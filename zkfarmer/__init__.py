#
# This file is part of the zkfarmer package.
# (c) Olivier Poitrey <rs@dailymotion.com>
#
# For the full copyright and license information, please view the LICENSE
# file that was distributed with this source code.

from watcher import ZkFarmJoiner, ZkFarmExporter


class ZkFarmer(object):
    def __init__(self, zkconn):
        self.zkconn = zkconn

    def join(self, zknode, conf):
        ZkFarmJoiner(self.zkconn, conf, zknode)

    def export(self, zknode, conf):
        ZkFarmExporter(self.zkconn, conf, zknode)

    def list(self, zknode):
        pass

    def set(self, zknode, field, value):
        pass

    def get(self, zknode, field):
        pass
