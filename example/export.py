import zc.zk
from zkfarmer.conf import ConfBase
from zkfarmer import ZkFarmer

class Farm(ConfBase):
    def write(self, nodes):
        print nodes

zkconn = zc.zk.ZooKeeper('localhost:2181')
farmer = ZkFarmer(zkconn)
farmer.export('/services/test', Farm())
