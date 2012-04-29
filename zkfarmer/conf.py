
# This file is part of the zkfarmer package.
# (c) Olivier Poitrey <rs@dailymotion.com>
#
# For the full copyright and license information, please view the LICENSE
# file that was distributed with this source code.

import os
import os.path
import shutil
import json
import yaml

# Prevent unstandard !!python/unicode prefixes
yaml.add_representer(unicode, lambda dumper, value: dumper.represent_scalar(u'tag:yaml.org,2002:str', value))


def Conf(file, format=None):
    if format:
        if format == 'json':
            return ConfJSON(file)
        elif format == 'yaml':
            return ConfYAML(file)
        elif format == 'php':
            return ConfPHP(file)
        elif format == 'dir':
            return ConfDir(file)
        else:
            raise ValueError('Unsupported format: %s' % format)
    else:
        if os.path.isdir(file):
            return ConfDir(file)
        else:
            ext = os.path.splitext(file)[1]
            if ext == '.json':
                return ConfJSON(file)
            elif ext == '.yaml':
                return ConfYAML(file)
            elif ext == '.php':
                return ConfPHP(file)
            else:
                raise ValueError('Cannot detect file format')


class ConfBase(object):
    def __init__(self, file_path):
        self.file_path = file_path

    def open(self, write=False):
        if self.file_path == '-':
            if write:
                return open('/dev/stdin', 'w')
            else:
                raise NotImplementedError('Cannot read configuration from stdin')
        mode = 'w' if write else 'r'
        return open(self.file_path, mode)

    def read(self):
        raise NotImplementedError('%s.read()' % self.__class__.__name__)

    def write(self, obj):
        raise NotImplementedError('%s.write()' % self.__class__.__name__)


class ConfJSON(ConfBase):
    def read(self):
        if os.path.exists(self.file_path):
            with self.open() as fd:
                return json.load(fd)

    def write(self, obj):
        try:
            if self.read() == obj:
                return
        except NotImplementedError:
            pass
        with self.open(write=True) as fd:
            json.dump(obj, fd)


class ConfYAML(ConfBase):
    def read(self):
        if os.path.exists(self.file_path):
            with self.open() as fd:
                return yaml.load(fd)

    def write(self, obj):
        try:
            if self.read() == obj:
                return
        except NotImplementedError:
            pass
        with self.open(write=True) as fd:
            yaml.dump(obj, fd, default_flow_style=False, allow_unicode=True)


class ConfPHP(ConfBase):
    meta = {'"': '\\"', "\0": "\\\0", "\n": "\\n", "\\": "\\\\"}
    indent = '    '

    def _quotemeta(self, value):
        return ''.join(self.meta.get(c, c) for c in value)

    def _dump(self, value, lvl=0):
        if type(value) == int:
            return value
        elif isinstance(value, (str, unicode)):
            return '"%s"' % self._quotemeta(value)
        elif type(value) == dict:
            indent = lvl * self.indent
            body = ',\n'.join(['%s"%s" => %s' % (indent + self.indent, self._quotemeta(key), self._dump(val, lvl + 1)) for key, val in value.items()])
            return 'array\n%s(\n%s\n%s)' % (indent, body, indent)
        elif type(value) == list:
            return 'array(%s)' % ','.join([self._dump(val) for val in value])
        else:
            raise TypeError('php_dump: cannot serialize value: %s' % type(value))

    def write(self, obj):
        with self.open(write=True) as fd:
            fd.write('<?php return %s;' % self._dump(obj))


class ConfDir(ConfBase):
    def _parse(self, path):
        struct = {}
        for entry in os.listdir(path):
            if entry[0] is '.':
                # Ignore UNIX "invisible files"
                continue
            entry_path = os.path.join(path, entry)
            if os.path.isdir(entry_path):
                struct[entry] = self._parse(entry_path)
            else:
                with open(entry_path) as fd:
                    try:
                        struct[entry] = fd.read().strip().encode('utf-8')
                    except UnicodeDecodeError:
                        # ignore invalid utf-8 files
                        pass
        return struct

    def _dump(self, obj, path):
        if type(obj) != dict:
            raise TypeError('dir_dump: invalid obj type: %s' % type(obj))

        for key, val in obj.items():
            entry_path = os.path.join(path, key)
            if isinstance(val, (str, unicode, int)):
                if os.path.isdir(entry_path):
                    shutil.rmtree(entry_path)
                elif os.path.exists(entry_path):
                    with open(entry_path) as fd:
                        if fd.read() == val:
                            continue
                with open(entry_path, 'w') as fd:
                    fd.write(val)
            elif type(val) == dict:
                if not os.path.isdir(entry_path):
                    try:
                        os.unlink(entry_path)
                    except OSError:
                        pass
                    os.mkdir(entry_path)
                self._dump(val, entry_path)
            else:
                raise TypeError('dir_dump: cannot serialize value: %s' % type(val))

        # Clean vanished entries at this level
        for entry in os.listdir(path):
            if entry not in obj:
                entry_path = os.path.join(path, entry)
                if os.path.isdir(entry_path):
                    shutil.rmtree(entry_path)
                else:
                    os.unlink(entry_path)

    def read(self):
        return self._parse(self.file_path)

    def write(self, obj):
        self._dump(obj, self.file_path)
