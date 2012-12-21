import unittest
from mock import Mock, patch
from socket import socket, AF_INET, SOCK_DGRAM

from zkfarmer import utils

class TestUtils(unittest.TestCase):

    def test_ip(self):
        """Check if we can get an IP address."""
        s = Mock()
        s.connect.return_value = None
        s.getsockname.return_value = ("10.1.1.2", 61477)
        with patch("zkfarmer.utils.socket") as socket_mock:
            socket_mock.return_value = s
            self.assertEqual(utils.ip(), "10.1.1.2")

    def test_serialize(self):
        """Various serialize tests"""
        self.assertEqual(utils.unserialize(utils.serialize({1: "2"})),
                         {"1": "2"})
        self.assertEqual(utils.unserialize(utils.serialize({1: "2", "aaa": "c"})),
                         {"1": "2", "aaa": "c"})
        self.assertEqual(utils.unserialize(utils.serialize({1: "2", 3: {"4": "5"}})),
                         {"1": "2", "3": {"4": "5"}})

if __name__ == '__main__':
    unittest.main()

