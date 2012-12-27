import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/..')

from zkfarmer.conf import ConfBase
from zkfarmer import ZkFarmer
from kazoo.client import KazooClient

class Farm(ConfBase):
    def write(self, nodes):
        print nodes

zkconn = KazooClient('localhost:2181')
farmer = ZkFarmer(zkconn)
farmer.export('/services/test', Farm())
