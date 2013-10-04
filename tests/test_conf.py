# -*- encoding: utf-8 -*-

import unittest
import tempfile
import shutil
import json
import yaml
import os
import sys
import stat

from mock import patch
from zkfarmer import conf

class TempDirectoryTestCase(unittest.TestCase):

    def _compat_assertIn(self, a, b):
        # Python 2.6 compat
        self.assertTrue(a in b)

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        if not hasattr(self, "assertIn"):
            self.assertIn = self._compat_assertIn
    def tearDown(self):
        shutil.rmtree(self.tmpdir)

class TestConf(unittest.TestCase):

    def test_bad_format(self):
        """Check if we get the right exception if we specify a bad format."""
        self.assertRaises(ValueError, conf.Conf, "dunno.txt", "inexistant")

    def test_bad_extension(self):
        """Check we get the right exception if we specify a bad extension."""
        self.assertRaises(ValueError, conf.Conf, "dunno.dunno")

class TestConfJSON(TempDirectoryTestCase):

    def test_json_write_from_extension(self):
        """Check we write JSON output when specifying `.json`."""
        name = "%s/test.json" % self.tmpdir
        a = conf.Conf(name)
        a.write({1: "cc"})
        with open(name) as f:
            self.assertEqual(json.load(f), {"1": "cc"})

    def test_json_write_from_format(self):
        """Check we write JSON output when specifying `json` format."""
        name = "%s/test.php" % self.tmpdir
        a = conf.Conf(name, "json")
        a.write({1: "cc"})
        with open(name) as f:
            self.assertEqual(json.load(f), {"1": "cc"})

    def test_json_write_nested(self):
        """Check we can write a more complex JSON output."""
        name = "%s/test.json" % self.tmpdir
        a = conf.Conf(name)
        a.write({1: "cc", "ccc": 14, "ddd": {3: 4}})
        with open(name) as f:
            self.assertEqual(json.load(f),
                             {"1": "cc", "ccc": 14,
                              "ddd": {"3": 4}})

    def test_json_read(self):
        """Check we can read from JSON file."""
        name = "%s/test.json" % self.tmpdir
        with open(name, "w") as f:
            json.dump({1: "cc"}, f)
        a = conf.Conf(name)
        self.assertEqual(a.read(), {"1": "cc"})

    def test_json_read_utf8(self):
        """Check we can read an UTF-8 encoded JSON file."""
        name = "%s/test.json" % self.tmpdir
        with open(name, "w") as f:
            f.write('["😍", 123]')
        a = conf.Conf(name)
        self.assertEqual(a.read(), ['😍'.decode('utf-8'), 123])

    def test_json_read_not_exist(self):
        """Check we get `None` when asking for an inexistant file."""
        name = "%s/test.json" % self.tmpdir
        a = conf.Conf(name)
        self.assertEqual(a.read(), None)

    def test_json_dont_update_if_no_change(self):
        """Check the file is not updated when there is no change."""
        name = "%s/test.json" % self.tmpdir
        with open(name, "w") as f:
            f.write('{             "1": "2"}')
        a = conf.Conf(name)
        a.write({"1": "2"})
        with open(name) as f:
            self.assertEqual(f.read(), '{             "1": "2"}')

    def test_json_write_to_stdout(self):
        """Check we can write the result to stdout."""
        with patch("sys.stdout", new=open("%s/out" % self.tmpdir, "w")) as mock:
            a = conf.Conf("-", "json")
            a.write({"1": "2"})
            with open("%s/out" % self.tmpdir) as f:
                self.assertEqual(json.load(f),
                                 {"1": "2"})

    def test_json_no_overwrite_on_failure(self):
        """Check we don't overwrite an existing file in case of failure."""
        name = "%s/test.json" % self.tmpdir
        a = conf.Conf(name)
        a.write({"1": "2"})
        # Write something invalid
        self.assertRaises(TypeError, a.write, json)
        self.assertEqual(a.read(), {"1": "2"})

    def test_json_appropriate_rights(self):
        """Check if a file is created with the appropriate rights"""
        os.umask(022)
        name = "%s/test.json" % self.tmpdir
        a = conf.Conf(name)
        a.write({"1": "2"})
        del a
        a = os.stat(name)
        self.assertEqual(a.st_mode & 0777, 0644)

    def test_json_appropriate_rights_umask(self):
        """Check if a file is created with appropriate rights using non standard umask."""
        os.umask(027)
        name = "%s/test.json" % self.tmpdir
        a = conf.Conf(name)
        a.write({"1": "2"})
        del a
        a = os.stat(name)
        self.assertEqual(a.st_mode & 0777, 0640)

class TestConfYAML(TempDirectoryTestCase):

    def test_yaml_write_from_extension(self):
        """Check we write YAML output when specifying `.yaml`."""
        name = "%s/test.yaml" % self.tmpdir
        a = conf.Conf(name)
        a.write({1: "cc"})
        with open(name) as f:
            self.assertEqual(yaml.load(f), {1: "cc"})

    def test_yaml_write_from_format(self):
        """Check we write YAML output when specifying `yaml` format."""
        name = "%s/test.php" % self.tmpdir
        a = conf.Conf(name, "yaml")
        a.write({1: "cc"})
        with open(name) as f:
            self.assertEqual(yaml.load(f), {1: "cc"})

    def test_yaml_write_nested(self):
        """Check we can write a more complex YAML output."""
        name = "%s/test.yaml" % self.tmpdir
        a = conf.Conf(name)
        a.write({1: "cc", "ccc": 14, "ddd": {"3": 4}})
        with open(name) as f:
            self.assertEqual(yaml.load(f),
                             {1: "cc", "ccc": 14,
                              "ddd": {"3": 4}})

    def test_yaml_read(self):
        """Check we can read from YAML file."""
        name = "%s/test.yaml" % self.tmpdir
        with open(name, "w") as f:
            yaml.dump({1: "cc"}, f)
        a = conf.Conf(name)
        self.assertEqual(a.read(), {1: "cc"})

    def test_yaml_read_not_exist(self):
        """Check we get `None` when asking for an inexistant file."""
        name = "%s/test.yaml" % self.tmpdir
        a = conf.Conf(name)
        self.assertEqual(a.read(), None)

    def test_yaml_dont_update_if_no_change(self):
        """Check the file is not updated when there is no change."""
        name = "%s/test.yaml" % self.tmpdir
        with open(name, "w") as f:
            f.write('{             "1": "2"}')
        a = conf.Conf(name)
        a.write({"1": "2"})
        with open(name) as f:
            self.assertEqual(f.read(), '{             "1": "2"}')

class TestConfPHP(TempDirectoryTestCase):

    def test_php_write_from_extension(self):
        """Check we write PHP output when specifying `.php`."""
        name = "%s/test.php" % self.tmpdir
        a = conf.Conf(name)
        a.write({"1": "cc"})
        with open(name) as f:
            self.assertIn('"1" => "cc"', f.read())

    def test_php_write_from_format(self):
        """Check we write PHP output when specifying `php` format."""
        name = "%s/test.yaml" % self.tmpdir
        a = conf.Conf(name, "php")
        a.write({"1": "cc"})
        with open(name) as f:
            self.assertIn('"1" => "cc"', f.read())

    def test_php_write_nested(self):
        """Check we can write a more complex PHP output."""
        name = "%s/test.php" % self.tmpdir
        a = conf.Conf(name)
        a.write({"1": "cc", "ccc": "14", "ddd": {"3": "4"}})
        with open(name) as f:
            result = f.read()
            self.assertIn('"1" => "cc"', result)
            self.assertIn('"3" => "4"', result)
            self.assertIn('"ddd" => array', result)

    def test_php_read(self):
        """Check we can't read PHP"""
        name = "%s/test.php" % self.tmpdir
        self.assertRaises(NotImplementedError, conf.Conf(name).read)

    def test_php_no_overwrite_on_failure(self):
        """Check we don't overwrite an existing file in case of failure."""
        name = "%s/test.json" % self.tmpdir
        a = conf.Conf(name)
        a.write({"1": "2"})
        # Write something invalid
        self.assertRaises(TypeError, a.write, json)
        self.assertEqual(a.read(), {"1": "2"})

    def test_php_write_list(self):
        """Check we can write a list correctly."""
        name = "%s/test.php" % self.tmpdir
        a = conf.Conf(name, "php")
        a.write({"something": [1,2,3]})
        with open(name) as f:
            self.assertIn('array(1,2,3)', f.read())

    def test_php_write_boolean(self):
        """Check we can handle booleans."""
        name = "%s/test.php" % self.tmpdir
        a = conf.Conf(name, "php")
        a.write({"something": True, "somethingelse": False})
        with open(name) as f:
            self.assertIn('true', f.read())
        with open(name) as f:
            self.assertIn('false', f.read())

    def test_php_utf8_encoded(self):
        """Check we get UTF-8 encoded output."""
        name = "%s/test.php" % self.tmpdir
        a = conf.Conf(name, "php")
        a.write(["ascii", "😍".decode("utf-8")])
        with open(name) as f:
            result = f.read()
            self.assertIn('"\xf0\x9f\x98\x8d"', result)

class TestConfDir(TempDirectoryTestCase):

    def test_dir_from_existence(self):
        """Check we use directory as output because the directory exists."""
        a = conf.Conf(self.tmpdir)
        a.write({"1": "cc"})
        with open("%s/1" % self.tmpdir) as f:
            self.assertEqual(f.read(), "cc")

    def test_dir_from_format(self):
        """Check we create the directory if we force the format."""
        name = "%s/test.php" % self.tmpdir
        a = conf.Conf(name, "dir")
        os.makedirs(name)
        a.write({"1": "cc"})
        with open("%s/1" % name) as f:
            self.assertEqual(f.read(), "cc")

    def test_dir_read(self):
        """Check we can read data from a directory."""
        with open("%s/stuff" % self.tmpdir, "w") as f:
            f.write("12")
        with open("%s/otherstuff" % self.tmpdir, "w") as f:
            f.write("13")
        a = conf.Conf(self.tmpdir)
        self.assertEqual(a.read(),
                         {"stuff": "12",
                          "otherstuff": "13"})

    def test_dir_read_nested(self):
        """Check we can read nested data in a directory."""
        os.makedirs("%s/otherstuff" % self.tmpdir)
        with open("%s/stuff" % self.tmpdir, "w") as f:
            f.write("12")
        with open("%s/otherstuff/stuff" % self.tmpdir, "w") as f:
            f.write("13")
        a = conf.Conf(self.tmpdir)
        self.assertEqual(a.read(),
                         {"stuff": "12",
                          "otherstuff": {"stuff": "13"}})

    def test_dir_write_nested(self):
        """Check we can write nested data in a directory."""
        a = conf.Conf(self.tmpdir)
        a.write({"stuff": "12",
                 "otherstuff": {"1": "1221",
                                "2": "1111"}})
        with open("%s/stuff" % self.tmpdir) as f:
            self.assertEqual(f.read(), "12")
        with open("%s/otherstuff/1" % self.tmpdir) as f:
            self.assertEqual(f.read(), "1221")
        with open("%s/otherstuff/2" % self.tmpdir) as f:
            self.assertEqual(f.read(), "1111")


if __name__ == '__main__':
    unittest.main()
