#
# This file is part of the zkfarmer package.
# (c) Olivier Poitrey <rs@dailymotion.com>
#
# For the full copyright and license information, please view the LICENSE
# file that was distributed with this source code.

from utils import serialize, unserialize
from socket import socket, gethostname, AF_INET, SOCK_DGRAM
from watchdog.observers import Observer
import zookeeper
import zc.zk
import logging
import threading


class ZkFarmWatcher(object):
    def __init__(self):
        self.cv = threading.Condition()
        self.handled = False

    def wait(self):
        while True:
            self.handled = False
            self.cv.wait(60)
            if self.handled:
                break

    def notify(self):
        self.handled = True
        self.cv.notify_all()


class ZkFarmExporter(ZkFarmWatcher):
    def __init__(self, zkconn, root_node_path, conf, updated_handler=None, filter_handler=None):
        super(ZkFarmExporter, self).__init__()
        self.watched_paths = {}

        while True:
            with self.cv:
                node_names = zkconn.get_children(root_node_path, self.get_watcher(root_node_path))
                new_conf = {}
                for name in node_names:
                    subnode_path = '%s/%s' % (root_node_path, name)
                    info = unserialize(zkconn.get(subnode_path, self.get_watcher(subnode_path))[0])
                    if not filter_handler or filter_handler(info):
                        new_conf[name] = info
                conf.write(new_conf)
                if updated_handler:
                    updated_handler()
                self.wait()

    def watcher(self, handle, type, state, path):
        with self.cv:
            if path in self.watched_paths:
                del self.watched_paths[path]
            self.notify()

    def get_watcher(self, path):
        if path not in self.watched_paths:
            self.watched_paths[path] = True
            return self.watcher


class ZkFarmJoiner(ZkFarmWatcher):
    def __init__(self, zkconn, root_node_path, conf):
        super(ZkFarmJoiner, self).__init__()
        self.update_remote_timer = None
        self.update_local_timer = None

        self.zkconn = zkconn
        self.conf = conf
        self.node_path = '%s/%s' % (root_node_path, self.myip())

        # force the hostname info key
        info = conf.read()
        info['hostname'] = gethostname()
        conf.write(info)

        zkconn.create_recursive(root_node_path, '', zc.zk.OPEN_ACL_UNSAFE)
        zkconn.create(self.node_path, serialize(conf.read()), zc.zk.OPEN_ACL_UNSAFE, zookeeper.EPHEMERAL)

        observer = Observer()
        observer.schedule(self, path=conf.file_path, recursive=True)
        observer.start()

        zkconn.get(self.node_path, self.node_watcher)

        while True:
            with self.cv:
                self.wait()

    def dispatch(self, event):
        with self.cv:
            current_conf = unserialize(self.zkconn.get(self.node_path)[0])
            new_conf = self.conf.read()
            if current_conf != new_conf:
                logging.info('Local conf changed')
                self.zkconn.set(self.node_path, serialize(new_conf))
            self.notify()

    def node_watcher(self, handle, type, state, path):
        with self.cv:
            current_conf = self.conf.read()
            new_conf = unserialize(self.zkconn.get(self.node_path, self.node_watcher)[0])
            if current_conf != new_conf:
                logging.info('Remote conf changed')
                self.conf.write(new_conf)
            self.notify()

    def myip(self):
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
