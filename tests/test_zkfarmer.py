import unittest
import json
from mock import patch

from zkfarmer.zkfarmer import ZkFarmer
from zkfarmer.utils import create_filter
from kazoo.testing import KazooTestCase
from kazoo.exceptions import BadVersionError

class TestZkFarmer(KazooTestCase):

    def test_list_nonexistent_node(self):
        """List a node which does not exist."""
        z = ZkFarmer(self.client)
        self.assertEqual(z.list("/something"), [])
        self.assertEqual(z.list("/something/else"), [])

    def test_list_some_children(self):
        """List several nodes to get children."""
        z = ZkFarmer(self.client)
        self.assertEqual(z.list("/"), [])
        self.client.ensure_path("/child1")
        self.client.ensure_path("/child2")
        self.client.ensure_path("/child3/child4/child5")
        children = z.list("/")
        children.sort()
        self.assertEqual(children, ["child1", "child2", "child3"])
        self.assertEqual(z.list("/child2"), [])
        self.assertEqual(z.list("/child3"), ["child4"])
        self.assertEqual(z.list("/child3/child4"), ["child5"])
        self.assertEqual(z.list("/child3/child4/child5"), [])

    def test_get_inexistent_node(self):
        """Get a node which does not exist."""
        z = ZkFarmer(self.client)
        self.assertEqual(z.get("/nothing"), {"size": 0})

    def test_get(self):
        """Get data from a regular node."""
        z = ZkFarmer(self.client)
        self.client.ensure_path("/something/here")
        self.client.set("/something/here", json.dumps({1:"2", 3:"4"}))
        self.assertEqual(z.get("/something/here"),
                         {"1": "2", "3": "4"})

    def test_get_with_children(self):
        """Get data from a regular node with children."""
        z = ZkFarmer(self.client)
        self.client.ensure_path("/something/here")
        self.client.ensure_path("/something/not")
        self.client.set("/something", json.dumps({1:"2", 3: "4"}))
        self.assertEqual(z.get("/something"),
                         {"1": "2", "3": "4"})

    def test_get_with_fields(self):
        """Get data and filter in some fields."""
        z = ZkFarmer(self.client)
        self.client.ensure_path("/something/mysql2")
        self.client.set("/something/mysql2",
                        json.dumps(dict(enabled="1", maintainance="0", weight="10")))
        self.assertEqual(z.get("/something/mysql2", ["enabled"]),
                         {"enabled": "1"})
        self.assertEqual(z.get("/something/mysql2", ["enabled", "maintainance"]),
                         {"enabled": "1", "maintainance": "0"})
        self.assertEqual(z.get("/something/mysql2", ["disabled", "maintainance"]),
                         {"disabled": None, "maintainance": "0"})

    def test_set(self):
        """Set some value."""
        z = ZkFarmer(self.client)
        self.client.ensure_path("/something")
        z.set("/something", "enabled", "1")
        z.set("/something", "maintainance", "0")
        z.set("/something", "weight", "10")
        self.assertEqual(z.get("/something"),
                         dict(enabled="1", maintainance="0", weight="10"))
        self.assertEqual(json.loads(self.client.get("/something")[0]),
                         dict(enabled="1", maintainance="0", weight="10"))

    def test_set_bad_version(self):
        """Set some value with a concurrent update."""
        z = ZkFarmer(self.client)
        self.client.ensure_path("/something")
        orig = self.client.retry
        # Simulate a BadVersionError
        with patch.object(self.client, 'retry') as mock:
            def fail_once(*args, **kwargs):
                mock.side_effect = orig
                raise BadVersionError("Baaaad")
            mock.side_effect = fail_once
            z.set("/something", "enabled", "1")
            z.set("/something", "maintainance", "0")
            z.set("/something", "weight", "10")
        self.assertEqual(z.get("/something"),
                         dict(enabled="1", maintainance="0", weight="10"))

    def test_check(self):
        """Check status of a znode"""
        z = ZkFarmer(self.client)
        self.client.ensure_path("/something")
        for i in range(10):
            self.client.ensure_path("/something/mysql%d" % i)
            self.client.set("/something/mysql%d" % i,
                            json.dumps({"stuff": "ok"}))
        self.client.set("/something", json.dumps({"size": 12}))
        self.assertEqual(z.check("/something", "3", "4")[0], z.STATUS_OK)
        self.assertEqual(z.check("/something", "3", "1")[0], z.STATUS_WARNING)
        self.assertEqual(z.check("/something", "2", "4")[0], z.STATUS_CRITICAL)
        self.assertEqual(z.check("/something", "2", "1")[0], z.STATUS_CRITICAL)
        self.assertEqual(z.check("/something", "20%", "4")[0], z.STATUS_OK)
        self.assertEqual(z.check("/something", "10%", "4")[0], z.STATUS_CRITICAL)
        self.assertEqual(z.check("/something", "20%")[0], z.STATUS_OK)

    def test_check_with_filter(self):
        """Check status of a znode with filters"""
        z = ZkFarmer(self.client)
        self.client.ensure_path("/something")
        for i in range(10):
            self.client.ensure_path("/something/mysql%d" % i)
            self.client.set("/something/mysql%d" % i,
                            json.dumps({"enabled": ((i == 0) and "0" or "1"),
                                        "weight": "%d" % (i+10)}))
        self.client.set("/something", json.dumps({"size": 12,
                                                  "running_filter": "enabled=1,weight>11"}))
        self.assertEqual(z.check("/something", "5")[0], z.STATUS_OK)
        self.assertEqual(z.check("/something", "4")[0], z.STATUS_CRITICAL)

if __name__ == '__main__':
    unittest.main()
