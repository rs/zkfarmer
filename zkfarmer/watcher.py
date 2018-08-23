#
# This file is part of the zkfarmer package.
# (c) Olivier Poitrey <rs@dailymotion.com>
#
# For the full copyright and license information, please view the LICENSE
# file that was distributed with this source code.

import threading
import Queue
import time
import itertools
import os
from socket import gethostname

import logging as _logging
logger = _logging.getLogger(__name__)

from watchdog.observers import Observer

from .utils import serialize, unserialize, ip
from kazoo.exceptions import NoNodeError, NodeExistsError, ZookeeperError
from kazoo.client import KazooState, KeeperState, OPEN_ACL_UNSAFE

class ZkFarmWatcher(object):

    # Each subclass should implement a FSM. EVENTS is a
    # dictionary. Each event is associated to a list of transition. A
    # transition is a dictionary with a tuple `(src, dst)`
    # (states). Initial event is always "initial". When a function
    # "execute_NAME", with NAME being the event, exists, it will be
    # executed.
    EVENTS = {}

    def __init__(self, zkconn):
        self.events = Queue.PriorityQueue()
        self.counter = itertools.count()
        self.zkconn = zkconn
        self.zkconn.add_listener(self._zkchange)
        self.state = "initial"

    def _zkchange(self, state):
        if state == KazooState.CONNECTED:
            logger.info("Now connected to Zookeeper")
            self.urgent_event("connection recovered")
        elif state == KazooState.LOST:
            logger.warn("Connection to Zookeeper lost")
            self.urgent_event("connection lost")
        elif state == KazooState.SUSPENDED:
            logger.warn("Connection to Zookeeper suspended")
            logger.debug("Connection is considered as lost")
            self.urgent_event("connection lost")

    def event(self, name, *args):
        """Signal a new event to the main thread"""
        self.events.put(((2, next(self.counter)), name, args))
    def urgent_event(self, name, *args):
        """Signal a new priority event to the main thread"""
        self.events.put(((1, next(self.counter)), name, args))

    def loop(self, count=None, timeout=10, ignore_unknown_transitions=False):
        errors = 0
        while count is None or count > 0:
            if count is not None:
                count -= 1

            # Process pending events
            try:
                priority, event, args = self.events.get(True, timeout=timeout)
            except Queue.Empty:
                continue

            transition = [t for t in self.EVENTS[event] if t[0] == self.state]
            if not transition:
                text = "unknown transition for event %r from state %r" % (event,
                                                                          self.state)
                logger.warn(text)
                if not ignore_unknown_transitions:
                    raise RuntimeError(text)
                continue
            transition = transition[0]
            logger.debug("Transition from %r to %r next to event %r" % (transition[0],
                                                                        transition[1],
                                                                         event))
            execute = None
            do = True
            execute = getattr(self, "exec_%s_from_%s" % (event.replace(" ", "_"),
                                                         transition[0].replace(" ", "_")),
                              None)
            if execute is None:
                execute = getattr(self, "exec_%s" % event.replace(" ", "_"),
                                  None)
            if execute is not None:
                try:
                    logger.debug("And execute the appropriate action %r" % execute)
                    if execute(*args) is False:
                        do = False
                    errors = 0
                except ZookeeperError as e:
                    logger.exception("Got a zookeeper exception, reschedule the transition")
                    self.events.put((priority, event, args))
                    do = False
                    errors += 1
                    if errors > 10:
                        logger.warn("Too many errors, wait a bit")
                        time.sleep(2)
                        errors = 7
            if do:
                self.state = transition[1]

class ZkFarmExporter(ZkFarmWatcher):

    # States:
    #   - initial: not ready, initial setup should be done
    #   - idle: initial setup has been done, ready to accept events
    #   - lost: connection to database has been lost
    EVENTS = { "initial setup":          [("initial",   "idle"),
                                          ("idle",      "idle")],
               "children modified":      [("idle",      "idle"),
                                          ("lost",      "lost")],
               "node modified":          [("idle",      "idle"),
                                          ("lost",      "lost")],
               "connection lost":        [("initial",   "lost"),
                                          ("idle",      "lost"),
                                          ("lost",      "lost")],
               "connection recovered":   [("lost",      "initial"),
                                          ("idle",      "initial"),
                                          ("initial",   "initial")] }

    def __init__(self, zkconn, root_node_path, conf, updated_handler=None, filter_handler=None):
        super(ZkFarmExporter, self).__init__(zkconn)
        self.root_node_path = root_node_path
        self.conf = conf
        self.updated_handler = updated_handler
        self.filter_handler = filter_handler

        self.event("initial setup")

    def watch_children(self, _):
        self.event("children modified")
    def watch_node(self, what):
        self.event("node modified", what)

    def get_watcher_node(self, path):
        if path in self.monitored:
            return None         # Already monitored
        self.monitored.append(path)
        return self.watch_node

    def exec_connection_recovered(self):
        """The connection is reestablished"""
        logger.info("Connnection with Zookeeper reestablished")
        self.event("initial setup")

    def exec_initial_setup(self):
        """Watch for new children"""
        self.monitored = []
        self.root_monitored = False
        try:
            self.zkconn.ensure_path(self.root_node_path, acl=OPEN_ACL_UNSAFE)
        except NodeExistsError:
            pass
        self.event("children modified")
    def exec_initial_setup_from_idle(self):
        # This may happen because we recovered the connection several times
        pass

    def exec_children_modified(self):
        self.root_monitored = False
    def exec_children_modified_from_idle(self):
        """A change has occurred on a child"""
        new_conf = {}
        nodes = self.zkconn.get_children(self.root_node_path,
                                         watch=(self.root_monitored and None or self.watch_children))
        for name in nodes:
            subnode_path = '%s/%s' % (self.root_node_path, name)
            info = unserialize(self.zkconn.get(subnode_path,
                                               watch=self.get_watcher_node(subnode_path))[0])
            if not self.filter_handler or self.filter_handler(info):
                new_conf[name] = info
        self.conf.write(new_conf)
        if self.updated_handler:
            self.updated_handler()

    def exec_node_modified(self, what):
        """A change has occurred inside the node"""
        self.monitored.remove(what.path)
        self.event("children modified")

class ZkFarmImporter(ZkFarmWatcher):

    #   - initial: not ready, all initial setup should be done
    #   - observer ready: not ready but observer is initialized
    #   - idle: initial setup has been done, ready to accept events
    #   - lost: connection to database has been lost
    EVENTS = { "initial setup":          [("initial",   "observer ready")],
               "initial znode setup":    [("observer ready", "idle"),
                                          ("idle",      "idle")],
               "znode modified":         [("idle",      "idle"),
                                          ("observer ready", "observer ready"),
                                          ("lost",      "lost")],
               "local modified":         [("idle",      "idle"),
                                          ("observer ready", "observer ready"),
                                          ("lost",      "lost")],
               "connection lost":        [("observer ready", "lost"),
                                          ("idle",      "lost"),
                                          ("lost",      "lost")],
               "connection recovered":   [("lost",      "observer ready"),
                                          ("observer ready", "observer ready")]}

    def __init__(self, zkconn, root_node_path, conf, common=False):
        super(ZkFarmImporter, self).__init__(zkconn)
        self.conf = conf
        self.common = common
        self.node_path = "%s/%s" % (root_node_path,
                                    common and "common" or ip())

        self.event("initial setup")

    def _safe_local_conf(self):
        """Return the current local configuration or {} on errors"""
        try:
            return self.conf.read() or {} # Maybe the file does not exist
        except Exception as e:
            logger.warn("Cannot read local configuration: %s" % e)
            return {}

    def exec_connection_recovered(self):
        """The connection is reestablished"""
        logger.info("Connnection with Zookeeper reestablished")
        self.event("initial znode setup")

    def exec_initial_setup(self):
        """Non-zookeeper related initial setup"""
        # Setup observer
        observer = Observer()
        path = self.conf.file_path
        if not os.path.isdir(path):
            path = os.path.dirname(os.path.realpath(path))
        observer.schedule(self, path=path, recursive=True)
        observer.start()

        self.mzxid = None
        self.event("initial znode setup")

    def exec_initial_znode_setup(self):
        """Initial setup of znode"""
        try:
            self.zkconn.ensure_path(os.path.dirname(self.node_path))
            self.zkconn.create(self.node_path, serialize(self._safe_local_conf()),
                               acl=OPEN_ACL_UNSAFE, ephemeral=(not self.common))
        except NodeExistsError:
            # Already exists.
            if self.common:
                # Remote content is authoritative
                self.event("znode modified")
            else:
                # Our content is authoritative.
                self.event("local modified")

    def exec_initial_znode_setup_from_idle(self):
        # This may happen because we recovered the connection several times
        pass

    def exec_local_modified(self):
        pass
    def exec_znode_modified(self):
        pass
    def exec_local_modified_from_idle(self):
        """Check a local modification"""
        current_conf = unserialize(self.zkconn.get(self.node_path)[0])
        try:
            new_conf = self.conf.read()
        except Exception as e:
            logger.warn("Ignoring invalid local configuration: %s" % e)
            return
        if current_conf != new_conf:
            logger.info('Local conf changed')
            logger.debug('Previous conf:   %r' % current_conf)
            logger.debug('New conf:        %r' % new_conf)
            s = self.zkconn.set(self.node_path, serialize(new_conf))
            self.mzxid = s.mzxid # Record latest mzxid

    def dispatch(self, event):
        """A local change has occured"""
        if hasattr(event, "src_path") and event.src_path.startswith(self.conf.file_path) \
           or hasattr(event, "dst_path") and event.dst_path.startswith(self.conf.file_path) \
           or hasattr(event, "dest_path") and event.dest_path.startswith(self.conf.file_path):
            self.event("local modified")

class ZkFarmJoiner(ZkFarmImporter):

    def __init__(self, zkconn, root_node_path, conf, common=False,
                 updated_handler=None):
        self.updated_handler = updated_handler
        super(ZkFarmJoiner, self).__init__(zkconn, root_node_path,
                                           conf, common)

    def watch_node(self, what):
        self.event("znode modified")

    def exec_initial_setup(self):
        """Non-zookeeper related initial setup"""
        # Force the hostname info key
        info = self._safe_local_conf()
        if not self.common:
            info['hostname'] = gethostname()
        self.conf.write(info)
        if self.updated_handler:
            self.updated_handler()

        super(ZkFarmJoiner, self).exec_initial_setup()

    def exec_initial_znode_setup(self):
        super(ZkFarmJoiner, self).exec_initial_znode_setup()
        # Setup the watcher
        self.zkconn.get(self.node_path, self.watch_node)
        self.monitored = True

    def exec_znode_modified(self):
        self.monitored = False

    def exec_znode_modified_from_idle(self):
        """Check remote modification"""
        try:
            current_conf = self.conf.read()
        except Exception as e:
            logger.warn("Ignoring incorrect local configuration: %s" % e)
            current_conf = {}
        try:
            new = self.zkconn.get(self.node_path,
                                  watch=(self.monitored and None or self.watch_node))
            if new[1].mzxid <= self.mzxid:
                logger.debug('Discard remote modification older than '
                             'latest local modification (%r <= %r)' % (new[1].mzxid, self.mzxid))
                return
            new_conf = unserialize(new[0])
            if current_conf != new_conf:
                logger.info('Remote conf changed')
                logger.debug('Previous conf: %r' % current_conf)
                logger.debug('New conf:      %r' % new_conf)
                self.conf.write(new_conf)
                if self.updated_handler:
                    self.updated_handler()
        except NoNodeError:
            logger.warn("not able to watch for node %s: not exist anymore" % self.node_path)

    def exec_connection_lost(self):
        """The connection might be closed here"""
        logger.debug("We have the client (session) state of " + self.zkconn.client_state)
        if self.zkconn.client_state == KeeperState.CLOSED:
            logger.error("Zookeeper connection has been dropped since the session is closed and maximum number of retries reached")
            self.zkconn.stop()
            exit(1)
