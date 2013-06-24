#
# This file is part of the zkfarmer package.
# (c) Olivier Poitrey <rs@dailymotion.com>
#
# For the full copyright and license information, please view the LICENSE
# file that was distributed with this source code.

from .utils import serialize, unserialize, dict_set_path, dict_filter, create_filter
from .watcher import ZkFarmJoiner, ZkFarmExporter

from kazoo.client import OPEN_ACL_UNSAFE
from kazoo.exceptions import NoNodeError, BadVersionError

class ZkFarmer(object):
    STATUS_OK = 0
    STATUS_WARNING = 1
    STATUS_CRITICAL = 2
    STATUS_UNKNOWN = 3

    def __init__(self, zkconn):
        self.zkconn = zkconn

    def join(self, zknode, conf):
        # Create farms ZkNode if doesn't already exists
        self.zkconn.retry(self.zkconn.ensure_path, zknode, acl=OPEN_ACL_UNSAFE)
        # If we are going to enlarged the farm max seen size, store it
        current_size = len(self.list(zknode)) + 1
        if current_size > self.get(zknode, 'size'):
            self.set(zknode, 'size', current_size)
        # Join the farm
        ZkFarmJoiner(self.zkconn, zknode, conf).loop(ignore_unknown_transitions=True)

    def export(self, zknode, conf, updated_handler=None, filters=None):
        ZkFarmExporter(self.zkconn, zknode, conf,
                       updated_handler,
                       filter_handler=create_filter(filters)).loop(ignore_unknown_transitions=True)

    def list(self, zknode):
        try:
            return self.zkconn.retry(self.zkconn.get_children, zknode)
        except NoNodeError:
            return []

    def get(self, zknode, field_or_fields=None):
        try:
            data = self.zkconn.retry(self.zkconn.get, zknode)[0]
        except NoNodeError:
            return {'size': 0}
        return dict_filter(unserialize(data), field_or_fields)

    def _save_safe(self, zknode, info, data):
        retry = 3
        while retry:
            try:
                self.zkconn.retry(self.zkconn.set, zknode, serialize(info), data[1].version)
                break
            except BadVersionError:
                # remove value changed since I get it, retry with fresh value
                retry = retry - 1
                pass

    def set(self, zknode, field, value):
        data = self.zkconn.get(zknode)
        info = unserialize(data[0])
        dict_set_path(info, field, value)
        self._save_safe(zknode, info, data)

    def unset(self, zknode, field):
        data = self.zkconn.get(zknode)        
        info = unserialize(data[0])
        if field in info:
            del info[field]
        self._save_safe(zknode, info, data)

    def check(self, zknode, max_failed_node, warn_failed_node=None):
        props = self.get(zknode)

        if 'size' not in props:
            return (self.STATUS_UNKNOWN, "No `size' property found for `%s' farm" % zknode)
        size = props['size']
        running = 0

        try:
            max_failed = size * float(max_failed_node[0:-1]) / 100 if max_failed_node[-1] == '%' else int(max_failed_node)
        except ValueError:
            return (self.STATUS_UNKNOWN, "Invalid `max_failed_node' argument format: %s" % max_failed_node)
        if warn_failed_node:
            try:
                warn_failed = size * float(warn_failed_node[0:-1]) / 100 if warn_failed_node[-1] == '%' else int(warn_failed_node)
            except ValueError:
                return (self.STATUS_UNKNOWN, "Invalid `warn_failed_node' argument format: %s" % warn_failed_node)
        else:
            warn_failed = None

        if 'running_filter' in props:
            filter_handler = create_filter(props['running_filter'])
            for name in self.list(zknode):
                info = self.get('%s/%s' % (zknode.rstrip('/'), name))
                if filter_handler(info):
                    running += 1
        else:
            running = len(self.list(zknode))

        failed = size - running
        if failed >= max_failed:
            status = self.STATUS_CRITICAL
        elif warn_failed and failed >= warn_failed:
            status = self.STATUS_WARNING
        else:
            status = self.STATUS_OK

        return (status, "%d/%d nodes running, %d nodes failing, max allowed %s" % (running, size, failed, max_failed_node))
