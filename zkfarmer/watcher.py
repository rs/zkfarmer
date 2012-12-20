#
# This file is part of the zkfarmer package.
# (c) Olivier Poitrey <rs@dailymotion.com>
#
# For the full copyright and license information, please view the LICENSE
# file that was distributed with this source code.

import logging
import threading
import Queue
import time
import itertools
from socket import socket, gethostname, AF_INET, SOCK_DGRAM

from watchdog.observers import Observer

from .utils import serialize, unserialize
from kazoo.exceptions import NoNodeError, NodeExistsError, ZookeeperError
from kazoo.client import KazooState, OPEN_ACL_UNSAFE

class ZkFarmWatcher(object):

    # Each subclass should implement a FSM. EVENTS is a
    # dictionary. Each event is associated to a list of transition. A
    # transition is a dictionary with a tuple `(src, dst)`
    # (states). Initial event is always "initial". When a function
    # "execute_NAME", with NAME being the event, exists, it will be
    # executed.
    EVENTS = {}

    def __init__(self, zkconn):
        self.events = Queue.Queue()
        self.counter = itertools.count()
        self.zkconn = zkconn
        self.zkconn.add_listener(self._zkchange)

    def _zkchange(self, state):
        if state == KazooState.CONNECTED:
            logging.info("Now connected to Zookeeper")
            self.urgent_event("connection recovered")
        elif state == KazooState.LOST:
            logging.warn("Connection to Zookeeper lost")
            self.urgent_event("connection lost")
        elif state == KazooState.SUSPENDED:
            logging.warn("Connection to Zookeeper suspended")
            self.urgent_event("connection suspended")

    def event(self, name, *args):
        """Signal a new event to the main thread"""
        self.events.put(((2, next(self.counter)), name, args))
    def urgent_event(self, name, *args):
        """Signal a new priority event to the main thread"""
        self.events.put(((1, next(self.counter)), name, args))

    def loop(self):
        self.state = "initial"
        errors = 0
        while True:
            # Process pending events
            try:
                priority, event, args = self.events.get(True, 10)
            except Queue.Empty:
                continue

            transition = [t for t in self.EVENTS[event] if t[0] == self.state]
            if not transition:
                logging.warn("unknown transition for event %r from state %s" % (event,
                                                                                self.state))
                continue
            transition = transition[0]
            logging.debug("Transition from %r to %r next to event %r" % (transition[0],
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
                    logging.debug("And execute the appropriate action %r" % execute)
                    if execute(*args) is False:
                        do = False
                    errors = 0
                except ZookeeperError, e:
                    logging.exception("Got a zookeeper exception, reschedule the transition")
                    self.events.put((priority, event, args))
                    do = False
                    errors += 1
                    if errors > 10:
                        logging.warn("Too many errors, wait a bit")
                        time.sleep(2)
                        errors = 7
            if do:
                self.state = transition[1]

class ZkFarmExporter(ZkFarmWatcher):

    # States:
    #   - initial: not ready, initial setup should be done
    #   - idle: initial setup has been done, ready to accept events
    #   - suspended: connection to Zookeeper is suspended
    #   - pending: connection to Zookeeper is suspended and some events
    #              have been triggered
    #   - lost: connection to database has been lost
    EVENTS = { "initial setup":          [("initial",   "idle")],
               "children modified":      [("idle",      "idle"),
                                          ("lost",      "lost"),
                                          ("suspended", "pending"),
                                          ("pending",   "pending")],
               "node modified":          [("idle",      "idle"),
                                          ("lost",      "lost"),
                                          ("suspended", "pending"),
                                          ("pending",   "pending")],
               "connection lost":        [("initial",   "lost"),
                                          ("idle",      "lost"),
                                          ("pending",   "lost"),
                                          ("suspended", "lost")],
               "connection suspended":   [("idle",      "suspended"),
                                          ("suspended", "suspended")],
               "connection recovered":   [("lost",      "initial"),
                                          ("suspended", "idle"),
                                          ("pending",   "idle"),
                                          ("initial",   "initial")] }

    def __init__(self, zkconn, root_node_path, conf, updated_handler=None, filter_handler=None):
        super(ZkFarmExporter, self).__init__(zkconn)
        self.root_node_path = root_node_path
        self.conf = conf
        self.updated_handler = updated_handler
        self.filter_handler = filter_handler

        self.event("initial setup")
        self.loop()

    def watch_children(self, _):
        self.event("children modified")
    def watch_node(self, what):
        self.event("node modified", what)

    def get_watcher_node(self, path):
        if path in self.monitored:
            return None         # Already monitored
        self.monitored.append(path)
        return self.watch_node

    def exec_connection_recovered_from_suspended(self):
        pass
    def exec_connection_recovered_from_pending(self):
        self.event("children modified")
    def exec_connection_recovered(self):
        """The connection is reestablished"""
        logging.info("Connnection with Zookeeper reestablished")
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

class ZkFarmJoiner(ZkFarmWatcher):

    # States:
    #   - initial: not ready, all initial setup should be done
    #   - observer ready: not ready but observer is initialized
    #   - idle: initial setup has been done, ready to accept events
    #   - suspended: connection to Zookeeper is suspended
    #   - pending: connection to Zookeeper is suspended and some events
    #              have been triggered
    #   - lost: connection to database has been lost
    EVENTS = { "initial setup":          [("initial",   "observer ready")],
               "initial znode setup":    [("observer ready", "idle")],
               "znode modified":         [("idle",      "idle"),
                                          ("lost",      "lost"),
                                          ("suspended", "pending"),
                                          ("pending",   "pending")],
               "local modified":         [("idle",      "idle"),
                                          ("lost",      "lost"),
                                          ("suspended", "pending"),
                                          ("pending",   "pending")],
               "connection lost":        [("observer ready", "lost"),
                                          ("idle",      "lost"),
                                          ("pending",   "lost"),
                                          ("suspended", "lost")],
               "connection suspended":   [("idle",      "suspended"),
                                          ("suspended", "suspended")],
               "connection recovered":   [("lost",      "observer ready"),
                                          ("suspended", "idle"),
                                          ("pending",   "idle"),
                                          ("observer ready", "observer ready")]}

    def __init__(self, zkconn, root_node_path, conf):
        super(ZkFarmJoiner, self).__init__(zkconn)
        self.node_path = "%s/%s" % (root_node_path, self.grab_ip())
        self.conf = conf

        self.event("initial setup")
        self.loop()

    def watch_node(self, what):
        self.event("znode modified")

    def exec_connection_recovered_from_suspended(self):
        pass
    def exec_connection_recovered_from_pending(self):
        # We didn't want to have too many states, trigger both events
        self.event("local modified")
        self.event("znode modified")
    def exec_connection_recovered(self):
        """The connection is reestablished"""
        logging.info("Connnection with Zookeeper reestablished")
        self.event("initial znode setup")

    def exec_initial_setup(self):
        """Non-zookeeper related initial setup"""
        # Force the hostname info key
        info = self.conf.read()
        info['hostname'] = gethostname()
        self.conf.write(info)

        # Setup observer
        observer = Observer()
        observer.schedule(self, path=self.conf.file_path, recursive=True)
        observer.start()

        self.event("initial znode setup")

    def exec_initial_znode_setup(self):
        """Initial setup of znode"""
        try:
            self.zkconn.create(self.node_path, serialize(self.conf.read()),
                               acl=OPEN_ACL_UNSAFE, ephemeral=True)
        except NodeExistsError:
            # Race condition, may happen
            pass
        # Setup the watcher
        self.zkconn.get(self.node_path, self.watch_node)
        self.monitored = True

    def exec_local_modified(self):
        pass
    def exec_local_modified_from_idle(self):
        """Check a local modification"""
        current_conf = unserialize(self.zkconn.get(self.node_path)[0])
        new_conf = self.conf.read()
        if current_conf != new_conf:
            logging.info('Local conf changed')
            self.zkconn.set(self.node_path, serialize(new_conf))

    def exec_znode_modified(self):
        self.monitored = False
    def exec_znode_modified_from_idle(self):
        """Check remote modification"""
        current_conf = self.conf.read()
        try:
            new_conf = unserialize(self.zkconn.get(self.node_path,
                                                   watch=(self.monitored and None or self.watch_node))[0])
            if current_conf != new_conf:
                logging.info('Remote conf changed')
                self.conf.write(new_conf)
        except NoNodeError:
            logging.warn("not able to watch for node %s: not exist anymore" % self.node_path)

    def dispatch(self, event):
        """A local change has occured"""
        self.event("local modified")

    def grab_ip(self):
        # Try to find default IP
        ip = None
        s = socket(AF_INET, SOCK_DGRAM)
        try:
            s.connect(('239.255.0.0', 9))
            ip = s.getsockname()[0]
        except socket.error:
            logging.error("Cannot determine host IP")
            exit(1)
        finally:
            del s
        return ip
