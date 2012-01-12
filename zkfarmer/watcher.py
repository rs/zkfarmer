#
# This file is part of the zkfarmer package.
# (c) Olivier Poitrey <rs@dailymotion.com>
#
# For the full copyright and license information, please view the LICENSE
# file that was distributed with this source code.

from socket import socket, AF_INET, SOCK_DGRAM
from watchdog.observers import Observer
import threading
import json


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
    def __init__(self, zkconn, conf, root_node_path):
        super(ZkFarmExporter, self).__init__()
        self.watched_paths = {}

        while True:
            with self.cv:
                node_names = zkconn.get_children(root_node_path, self.get_watcher(root_node_path))
                nodes = {}
                for name in node_names:
                    subnode_path = '%s/%s' % (root_node_path, name)
                    nodes[name] = zkconn.get(subnode_path, self.get_watcher(subnode_path))[0]
                    try:
                        nodes[name] = json.loads(nodes[name])
                    except ValueError:
                        pass
                conf.write(nodes)
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
    ZOO_OPEN_ACL_UNSAFE = {"perms": 0x1f, "scheme": "world", "id": "anyone"}

    def __init__(self, zkconn, conf, root_node_path):
        super(ZkFarmJoiner, self).__init__()
        self.conf_changed = False
        self.conf_ignore_next = False
        self.node_changed = False
        self.node_ignore_next = False

        node_path = '%s/%s' % (root_node_path, self.myip())

        zkconn.create(node_path, json.dumps(conf.read()), [self.ZOO_OPEN_ACL_UNSAFE], zookeeper.EPHEMERAL)

        observer = Observer()
        observer.schedule(self, path=conf.file_path, recursive=True)
        observer.start()

        zkconn.get(node_path, self.node_watcher)

        while True:
            with self.cv:
                if self.conf_changed and self.node_changed:
                    logging.warn('Got conflict, both ends modified, enforce local')
                if self.conf_changed:
                    if self.conf_ignore_next:
                        self.conf_ignore_next = False
                    else:
                        logging.info('Local conf changed')
                        self.node_ignore_next = True
                        zkconn.set(node_path, json.dumps(conf.read()))
                elif self.node_changed:
                    data = zkconn.get(node_path, self.node_watcher)[0]
                    if self.node_ignore_next:
                        self.node_ignore_next = False
                    else:
                        logging.info('Remote conf changed')
                        self.conf_ignore_next = True
                        conf.write(json.loads(data))
                self.conf_changed = False
                self.node_changed = False
                self.wait()

    def dispatch(self, event):
        with self.cv:
            self.conf_changed = True
            self.notify()

    def node_watcher(self, handle, type, state, path):
        with self.cv:
            self.node_changed = True
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
