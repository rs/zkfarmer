import unittest

from zkfarmer.utils import create_filter

class TestFilters(unittest.TestCase):

    def test_simple_filter(self):
        """Check if a simple equality filter works."""
        filter = create_filter("enable=1")
        self.assertTrue(filter(dict(enable="1")))
        self.assertFalse(filter(dict(enable="0")))
        self.assertFalse(filter(dict(notenabled="1")))
        self.assertFalse(filter(dict(notenabled="1", something="18")))
        self.assertFalse(filter(dict(something="19", enable="0")))
        self.assertTrue(filter(dict(something="19", enable="1")))
        self.assertTrue(filter(dict(something="19", enable="1", somethingelse="1")))

    def test_two_equalities(self):
        """Check if a filter with two equalities works."""
        filter = create_filter("enable=1,maintainance=0")
        self.assertTrue(filter(dict(enable="1", maintainance="0")))
        self.assertTrue(filter(dict(enable="1", maintainance="0", somethingelse="43")))
        self.assertFalse(filter(dict(enable="0", maintainance="0", somethingelse="43")))
        self.assertFalse(filter(dict(enable="1", maintainance="1", somethingelse="43")))
        self.assertFalse(filter(dict(enable="1", somethingelse="43")))

    def test_existence(self):
        """Check if filters on existence work."""
        filter = create_filter("enable=1,working")
        self.assertTrue(filter(dict(enable="1",working="0")))
        self.assertTrue(filter(dict(enable="1",working="1")))
        self.assertTrue(filter(dict(enable="1",working="1",notworking="1")))
        self.assertFalse(filter(dict(enable="0",working="1")))
        self.assertFalse(filter(dict(enable="1",notworking="1")))

    def test_inexistence(self):
        """Check if filters on inexistence work."""
        filter = create_filter("enable=1,!working")
        self.assertFalse(filter(dict(enable="1",working="0")))
        self.assertFalse(filter(dict(enable="1",working="1")))
        self.assertFalse(filter(dict(enable="1",working="1",notworking="1")))
        self.assertFalse(filter(dict(enable="0",working="1")))
        self.assertTrue(filter(dict(enable="1",notworking="1")))
        self.assertFalse(filter(dict(enable="0",notworking="1")))

    def test_inequalities(self):
        """Check if filters with inequalities work."""
        filter = create_filter("enable=1,weight>20")
        self.assertTrue(filter(dict(enable="1",weight="21")))
        self.assertTrue(filter(dict(enable="1",weight="121")))
        self.assertFalse(filter(dict(enable="1",weight="1")))
        self.assertFalse(filter(dict(enable="1",weight="20")))
        self.assertFalse(filter(dict(enable="0",weight="21")))
        self.assertFalse(filter(dict(enable="1")))
        filter = create_filter("enable=1,weight>=20")
        self.assertTrue(filter(dict(enable="1",weight="20")))
        self.assertFalse(filter(dict(enable="1",weight="19")))
        self.assertTrue(filter(dict(enable="1",weight="21")))
        filter = create_filter("enable=1,weight<=20")
        self.assertTrue(filter(dict(enable="1",weight="20")))
        self.assertTrue(filter(dict(enable="1",weight="19")))
        self.assertFalse(filter(dict(enable="1",weight="21")))
        filter = create_filter("enable=1,weight<20")
        self.assertFalse(filter(dict(enable="1",weight="20")))
        self.assertTrue(filter(dict(enable="1",weight="19")))
        self.assertFalse(filter(dict(enable="1",weight="21")))
        filter = create_filter("enable=1,weight!=20")
        self.assertFalse(filter(dict(enable="1",weight="20")))
        self.assertTrue(filter(dict(enable="1",weight="19")))
        self.assertTrue(filter(dict(enable="1",weight="121")))
        self.assertFalse(filter(dict(enable="1")))

    def test_empty_filter(self):
        """Check if an empty filter works."""
        filter = create_filter("")
        # All is true
        self.assertTrue(filter({1: 2}))
        self.assertTrue(filter({}))
        self.assertTrue(filter({3: 4}))

    def test_nested_filter(self):
        """Check if a filter on nested elements works."""
        filter = create_filter("enable=1,mysql.replication_delay<20")
        self.assertTrue(filter(dict(enable="1", mysql=dict(replication_delay="10"))))
        self.assertFalse(filter(dict(enable="1", mysql=dict(replication_delay="30"))))
        self.assertFalse(filter(dict(enable="0", mysql=dict(replication_delay="10"))))
        self.assertFalse(filter(dict(enable="1")))

if __name__ == '__main__':
    unittest.main()
