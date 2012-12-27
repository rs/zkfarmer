import unittest
import json

from zkfarmer.conf import ConfJSON
from zkfarmer.watcher import ZkFarmExporter
from zkfarmer.utils import create_filter
from kazoo.testing import KazooTestCase
from mock import Mock

class TestZkExporter(KazooTestCase):

    TIMEOUT=0.1

    def setUp(self):
        KazooTestCase.setUp(self)
        self.conf = Mock(spec=ConfJSON)

    def test_start_empty(self):
        """Test we get nothing when nothing is in ZooKeeper"""
        z = ZkFarmExporter(self.client, "/services/db", self.conf)
        z.loop(2, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({})
        return z

    def test_start_one_value(self, z=None):
        """Test we get something when Zookeeper starts with one value"""
        self.client.ensure_path("/services/db/1.1.1.1")
        self.client.set("/services/db/1.1.1.1",
                        json.dumps({"enabled": "1"}))
        if z is None:
            z = ZkFarmExporter(self.client, "/services/db", self.conf)
        z.loop(2, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({"1.1.1.1": {"enabled": "1"}})
        return z

    def test_start_several_values(self):
        """Test we get something when Zookeeper starts with several values"""
        for ip in ["1.1.1.1", "2.2.2.2", "3.3.3.3"]:
            self.client.ensure_path("/services/db/%s" % ip)
            self.client.set("/services/db/%s" % ip,
                            json.dumps({"enabled": "1",
                                        "ip": ip}))
        z = ZkFarmExporter(self.client, "/services/db", self.conf)
        z.loop(2, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({"1.1.1.1": {"enabled": "1", "ip": "1.1.1.1"},
                                            "2.2.2.2": {"enabled": "1", "ip": "2.2.2.2"},
                                            "3.3.3.3": {"enabled": "1", "ip": "3.3.3.3"}})

    def test_add_znode(self):
        """Test a new znode get noticied"""
        z = self.test_start_empty()
        self.test_start_one_value(z)

    def test_modify_znode(self):
        """Test a modification to an existing znode gets noticied"""
        z = self.test_start_one_value()
        self.client.set("/services/db/1.1.1.1",
                        json.dumps({"enabled": "0"}))
        z.loop(2, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({"1.1.1.1": {"enabled": "0"}})

    def test_updated_handler_called(self):
        """Test the appropriate handler is called on modification"""
        self.client.ensure_path("/services/db/1.1.1.1")
        self.client.set("/services/db/1.1.1.1",
                        json.dumps({"enabled": "1"}))
        handler = Mock()
        z = ZkFarmExporter(self.client, "/services/db", self.conf, handler)
        z.loop(2, timeout=self.TIMEOUT)
        self.client.set("/services/db/1.1.1.1",
                        json.dumps({"enabled": "0"}))
        z.loop(1, timeout=self.TIMEOUT)
        handler.assert_called_once_with()

    def test_filter(self):
        """Test filters are correctly applied"""
        self.client.ensure_path("/services/db/1.1.1.1")
        self.client.ensure_path("/services/db/2.2.2.2")
        self.client.ensure_path("/services/db/3.3.3.3")
        self.client.ensure_path("/services/db/4.4.4.4")
        self.client.set("/services/db/1.1.1.1",
                        json.dumps({"enabled": "0", "weight": "20"}))
        self.client.set("/services/db/2.2.2.2",
                        json.dumps({"enabled": "1", "weight": "20"}))
        self.client.set("/services/db/3.3.3.3",
                        json.dumps({"enabled": "1", "weight": "10"}))
        self.client.set("/services/db/4.4.4.4",
                        json.dumps({"enabled": "1", "weight": "30"}))
        z = ZkFarmExporter(self.client, "/services/db", self.conf,
                           filter_handler=create_filter("enabled=1,weight>15"))
        z.loop(2, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({"2.2.2.2": {"enabled": "1", "weight": "20"},
                                            "4.4.4.4": {"enabled": "1", "weight": "30"}})

    def test_disconnect(self):
        """Test disconnection to ZooKeeper is handled correctly"""
        self.client.ensure_path("/services/db/1.1.1.1")
        self.client.set("/services/db/1.1.1.1",
                        json.dumps({"enabled": "1"}))
        z = ZkFarmExporter(self.client, "/services/db", self.conf)
        z.loop(2, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({"1.1.1.1": {"enabled": "1"}})
        self.conf.reset_mock()
        self.expire_session()
        z.loop(10, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({"1.1.1.1": {"enabled": "1"}})

    def test_disconnect_and_still_works(self):
        """Test disconnection to Zookeeper does not disrupt the exporter"""
        self.client.ensure_path("/services/db/1.1.1.1")
        self.client.set("/services/db/1.1.1.1",
                        json.dumps({"enabled": "1"}))
        z = ZkFarmExporter(self.client, "/services/db", self.conf)
        z.loop(2, timeout=self.TIMEOUT)
        self.expire_session()
        z.loop(10, timeout=self.TIMEOUT)
        self.client.set("/services/db/1.1.1.1",
                        json.dumps({"enabled": "2"}))
        z.loop(2, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({"1.1.1.1": {"enabled": "2"}})


if __name__ == '__main__':
    unittest.main()
