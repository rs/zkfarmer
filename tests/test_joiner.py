import unittest
import json
from nose.plugins.skip import SkipTest

from zkfarmer.conf import ConfJSON
from zkfarmer.watcher import ZkFarmJoiner
from zkfarmer.utils import create_filter
from kazoo.testing import KazooTestCase
from mock import Mock, patch

class FakeFileEvent(object):
    """Fake event for fake watchdog observer"""
    src_path = "/fake/root"

class TestZkJoiner(KazooTestCase):

    NAME = "zk-test"
    IP = "1.1.1.1"
    TIMEOUT = 0.1

    def addCleanup(self, function):
        # On Python 2.6, we don't have this function. Try to implement
        # a degraded version of it.
        try:
            super(TestZkJoiner, self).addCleanup(function)
        except AttributeError:
            # We don't have that, maybe Python 2.6
            self._compat_cleanups.append(function)

    def setUp(self):
        super(TestZkJoiner, self).setUp()
        self.conf = Mock(spec=ConfJSON)
        self.conf.file_path = "/fake/root"

        self._compat_cleanups = []

        # Fake observer
        patcher = patch("zkfarmer.watcher.Observer", spec=True)
        self.mock_observer = patcher.start().return_value
        self.addCleanup(patcher.stop)

        # Fake IP
        patcher = patch("zkfarmer.watcher.ip")
        patcher.start().return_value = self.IP
        self.addCleanup(patcher.stop)

        # Fake name
        patcher = patch("zkfarmer.watcher.gethostname")
        patcher.start().return_value = self.NAME
        self.addCleanup(patcher.stop)

    def tearDown(self):
        while self._compat_cleanups:
            f = self._compat_cleanups.pop(-1)
            try:
                f()
            except KeyboardInterrupt:
                raise
            except:
                # To complex to implement correctly.
                pass
        return super(TestZkJoiner, self).tearDown()

    def test_inexisting_conf(self):
        """Test we can work when the configuration does not exist yet."""
        self.conf.read.return_value = None
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({"hostname": self.NAME})

    def test_initialize_observer(self):
        """Test if observer is correctly initialized"""
        self.conf.read.return_value = {}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.mock_observer.schedule.assert_called_once_with(z, path="/fake", recursive=True)
        self.mock_observer.start.assert_called_once_with()

    def test_set_hostname(self):
        """Check if hostname is correctly set into configuration file"""
        self.conf.read.return_value = {"enabled": "1"}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(1, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({"enabled": "1",
                                            "hostname": self.NAME})

    def test_initial_set(self):
        """Check if znode is correctly created into ZooKeeper"""
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.assertEqual(json.loads(self.client.get("/services/db/%s" % self.IP)[0]),
                         {"enabled": "1",
                          "hostname": self.NAME})

    def test_initial_set_ephemereal(self):
        """Check if created znode is ephemereal"""
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(2, timeout=self.TIMEOUT)
        self.assertEqual(self.client.get("/services/db/%s" % self.IP)[1].ephemeralOwner,
                         self.client.client_id[0])

    def test_initial_znode_already_exists(self):
        """Check if we created znode even if it exists"""
        self.client.ensure_path("/services/db/%s" % self.IP)
        self.client.set("/services/db/%s" % self.IP,
                        json.dumps({"enabled": "1"}))
        self.test_initial_set()

    def test_local_modification(self):
        """Check if ZooKeeper is updated after a local modification"""
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.conf.reset_mock()
        self.conf.read.return_value = {"enabled": "0",
                                       "hostname": self.NAME}
        z.dispatch(FakeFileEvent())
        z.loop(4, timeout=self.TIMEOUT)
        self.assertFalse(self.conf.write.called)
        self.assertEqual(json.loads(self.client.get("/services/db/%s" % self.IP)[0]),
                         {"enabled": "0",
                          "hostname": self.NAME})

    def test_detect_file_moved(self):
        """Test if we can detect a file moved into our location."""
        self.conf.read.return_value = {"enabled": "56",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.conf.reset_mock()
        self.conf.read.return_value = {"enabled": "57",
                                       "hostname": self.NAME}
        f = FakeFileEvent()
        f.src_path="/unrelated/path"
        f.dst_path="/fake/root"
        z.dispatch(f)
        z.loop(4, timeout=self.TIMEOUT)
        self.assertFalse(self.conf.write.called)
        self.assertEqual(json.loads(self.client.get("/services/db/%s" % self.IP)[0]),
                         {"enabled": "57",
                          "hostname": self.NAME})

    def test_zookeeper_modification(self):
        """Check if local configuration is updated after remote modification"""
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.conf.reset_mock()
        self.client.set("/services/db/%s" % self.IP,
                        json.dumps({"enabled": "0",
                                    "hostname": self.NAME}))
        z.loop(2, timeout=self.TIMEOUT)
        self.conf.write.assert_called_once_with({"enabled": "0",
                                                 "hostname": self.NAME})

    def test_no_write_when_no_modification(self):
        """Check we don't write modification if not needed"""
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.conf.reset_mock()
        self.conf.read.return_value = {"enabled": "0",
                                       "hostname": self.NAME}
        self.client.set("/services/db/%s" % self.IP,
                        json.dumps({"enabled": "0",
                                    "hostname": self.NAME}))
        z.loop(2, timeout=self.TIMEOUT)
        self.assertFalse(self.conf.write.called)

    def test_disconnect(self):
        """Test we handle a disconnect correctly"""
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.expire_session()
        z.loop(8, timeout=self.TIMEOUT)
        self.assertEqual(json.loads(self.client.get("/services/db/%s" % self.IP)[0]),
                         {"enabled": "1",
                          "hostname": self.NAME})
        return z

    def test_disconnect_and_local_modification(self):
        """Test we handle disconnect and local modification after reconnect"""
        z = self.test_disconnect()
        self.conf.reset_mock()
        self.conf.read.return_value = {"enabled": "0",
                                       "hostname": self.NAME}
        z.dispatch(FakeFileEvent())
        z.loop(4, timeout=self.TIMEOUT)
        self.assertFalse(self.conf.write.called)
        self.assertEqual(json.loads(self.client.get("/services/db/%s" % self.IP)[0]),
                         {"enabled": "0",
                          "hostname": self.NAME})

    def test_disconnect_and_remote_modification(self):
        """Test we handle disconnect and remote modification after reconnect"""
        z = self.test_disconnect()
        self.conf.reset_mock()
        self.client.set("/services/db/%s" % self.IP,
                        json.dumps({"enabled": "22",
                                    "hostname": self.NAME}))
        z.loop(2, timeout=self.TIMEOUT)
        self.conf.write.assert_called_once_with({"enabled": "22",
                                                 "hostname": self.NAME})

    def test_disconnect_while_local_modification(self):
        """Test we can disconnect and have a local modification while disconnected"""
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.expire_session()
        self.conf.read.return_value = {"enabled": "22",
                                       "hostname": self.NAME}
        z.dispatch(FakeFileEvent())
        z.loop(10, timeout=self.TIMEOUT)
        self.assertEqual(json.loads(self.client.get("/services/db/%s" % self.IP)[0]),
                         {"enabled": "22",
                          "hostname": self.NAME})

    def test_disconnect_while_remote_modification(self):
        """Test we can disconnect and have a remote modification while disconnected"""
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.expire_session()
        self.client.ensure_path("/services/db/%s" % self.IP) # Disconnected, the path does not exist
        self.client.set("/services/db/%s" % self.IP,
                        json.dumps({"enabled": "22",
                                    "hostname": self.NAME}))
        z.loop(10, timeout=self.TIMEOUT)
        try:
            self.assertEqual(json.loads(self.client.get("/services/db/%s" % self.IP)[0]),
                             {"enabled": "22",
                              "hostname": self.NAME})
        except AssertionError:
            # This test could be fixed but we won't because we
            # consider that the local filesystem is authoritative. If
            # this test succeeds, we can make it fail by stopping
            # zkfarmer before reconnection to ZooKeeper. In this case,
            # on next start, ZooKeeper modifications would be
            # lost. Moreover, the znode is ephemeral, so no "remote"
            # modifications can happend while the node is down.
            raise SkipTest("Fuzzy test")

    def test_disconnect_while_both_remote_and_local_modification(self):
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.expire_session()
        z.dispatch(FakeFileEvent())
        self.conf.read.return_value = {"enabled": "56",
                                       "hostname": self.NAME}
        self.client.ensure_path("/services/db/%s" % self.IP) # Disconnected, the path does not exist
        self.client.set("/services/db/%s" % self.IP,
                        json.dumps({"enabled": "22",
                                    "hostname": self.NAME}))
        z.loop(10, timeout=self.TIMEOUT)
        self.assertEqual(json.loads(self.client.get("/services/db/%s" % self.IP)[0]),
                         {"enabled": "56",
                          "hostname": self.NAME})

    def test_remote_modification_should_not_cancel_local_one(self):
        """Test if a received remote modification does not cancel a local one.

        This may happen if we have a local modification while
        processing the echo of a previous modification. For example,
        we set a value to 1021, we receive back a remote change about
        this value being set to 1021 but we have a local modification
        at the same time putting the value to 1022.
        """
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME,
                                       "counter": 1000}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf)
        z.loop(3, timeout=self.TIMEOUT)
        self.conf.reset_mock()
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME,
                                       "counter": 1001}
        z.dispatch(FakeFileEvent())
        z.loop(1, timeout=self.TIMEOUT)
        # Here comes the local modification that won't be noticed now
        self.conf.reset_mock()
        self.conf.read.return_value = {"enabled": "1",
                                       "hostname": self.NAME,
                                       "counter": 1002}
        z.loop(3, timeout=self.TIMEOUT)
        self.assertFalse(self.conf.write.called)

    def test_common_node(self):
        """Check we can request a common node"""
        self.conf.read.return_value = {"enabled": "1",
                                       "maintainance": "2"}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf, True)
        z.loop(3, timeout=self.TIMEOUT)
        # Check we don't get the hostname
        self.conf.write.assert_called_with({"enabled": "1",
                                            "maintainance": "2"})
        # Check the node exists
        n = self.client.get("/services/db/common")
        self.assertEqual(n[0],
                         json.dumps({"enabled": "1",
                                     "maintainance": "2"}))
        self.assertEqual(n[1].ephemeralOwner, 0)

    def test_common_node_join_when_local_modifications(self):
        """Check that we get remote modification when using a common node"""
        self.conf.read.return_value = { "enabled": "1" }
        self.client.ensure_path("/services/db/common")
        self.client.set("/services/db/common", json.dumps({ "enabled": "42" }))
        z = ZkFarmJoiner(self.client, "/services/db", self.conf, True)
        z.loop(3, timeout=self.TIMEOUT)
        self.conf.write.assert_called_with({ "enabled": "42" })
        n = self.client.get("/services/db/common")
        self.assertEqual(n[0],
                         json.dumps({"enabled": "42"}))

    def test_common_node_disconnect_and_local_modifications(self):
        """Check that remote modifications take over local modifications for a common node"""
        self.conf.read.return_value = {"enabled": "1"}
        z = ZkFarmJoiner(self.client, "/services/db", self.conf, True)
        z.loop(3, timeout=self.TIMEOUT)
        self.expire_session()
        self.conf.read.return_value = {"enabled": "22"}
        z.dispatch(FakeFileEvent())
        z.loop(10, timeout=self.TIMEOUT)
        self.assertEqual(json.loads(self.client.get("/services/db/common")[0]),
                         {"enabled": "1"})
