#
# This file is part of the zkfarmer package.
# (c) Olivier Poitrey <rs@dailymotion.com>
#
# For the full copyright and license information, please view the LICENSE
# file that was distributed with this source code.

from watcher import ZkFarmJoiner, ZkFarmExporter
from zookeeper import BadVersionException
from utils import serialize, unserialize, dict_set_path, dict_filter, create_filter


class ZkFarmer(object):
    def __init__(self, zkconn):
        self.zkconn = zkconn

    def join(self, zknode, conf):
        ZkFarmJoiner(self.zkconn, zknode, conf)

    def export(self, zknode, conf, updated_handler=None, filters=None):
        ZkFarmExporter(self.zkconn, zknode, conf, updated_handler, filter_handler=create_filter(filters))

    def list(self, zknode):
        return self.zkconn.get_children(zknode)

    def get(self, zknode, field_or_fields=None):
        data = self.zkconn.get(zknode)[0]
        return dict_filter(unserialize(data), field_or_fields)

    def set(self, zknode, field, value):
        retry = 3
        while retry:
            data = self.zkconn.get(zknode)
            info = unserialize(data[0])
            dict_set_path(info, field, value)
            try:
                self.zkconn.set(zknode, serialize(info), data[1]['version'])
                break
            except BadVersionException:
                # remove value changed since I get it, retry with fresh value
                retry = retry - 1
                pass
