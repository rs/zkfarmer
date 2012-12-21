import json
import operator
import logging
import re
import time
from socket import socket, gethostname, AF_INET, SOCK_DGRAM

logger = logging.getLogger(__name__)

def ip():
    """Find default IP"""
    ip = None
    s = socket(AF_INET, SOCK_DGRAM)
    try:
        s.connect(('239.255.0.0', 9))
        ip = s.getsockname()[0]
    except socket.error:
        raise RuntimeError("Cannot determine host IP")
    finally:
        del s
    return ip

def serialize(data):
    try:
        if type(data) != dict:
            raise TypeError('Must be a dict')
        return json.dumps(data)
    except Exception, e:
        logger.warn('Cannot serialize: %s [%s]', data, e)
        return '{}'


def unserialize(serialized):
    if not serialized:
        return {}
    try:
        data = json.loads(serialized)
        if type(data) != dict:
            raise TypeError('Not a dict')
        return data
    except Exception, e:
        logger.warn('Cannot unserialize: %s [%s]', serialized, e)
        return {}


def dict_get_path(the_dict, path):
    try:
        return reduce(operator.getitem, [the_dict] + path.split('.'))
    except:
        return None


def dict_set_path(the_dict, path, value):
    current = the_dict
    for component in path.split('.')[:-1]:
        if component not in current or type(current[component]) != dict:
            current[component] = {}
        current = current[component]
    current[path.split('.')[-1]] = value


def dict_filter(the_dict, field_or_fields=None):
    if field_or_fields is None:
        return the_dict
    elif type(field_or_fields) == list:
        fields = {}
        for f in field_or_fields:
            fields[f] = dict_get_path(the_dict, f)
        return fields
    elif isinstance(field_or_fields, (str, unicode)):
        return dict_get_path(the_dict, field_or_fields)
    else:
        raise TypeError('Invalid type for field path: %s' % type(field_or_fields))


def get_operator(op):
    try:
        return {"==": operator.eq,
                "=":  operator.eq,
                "!=": operator.ne,
                ">=": operator.ge,
                "<=": operator.le,
                ">":  operator.gt,
                "<":  operator.lt}[op]
    except KeyError:
        raise ValueError('Unknown operator: %s' % op)


def match_predicates(predicates, the_dict):
    for predicate in predicates:
        m1, m2 = (dict_get_path(the_dict, predicate['path']), predicate['value'])
        if m1 is None and m2 is not None:
            return False
        try:
            int(m1)
            int(m2)
            m1 = int(m1)
            m2 = int(m2)
        except (ValueError, TypeError):
            pass
        if not predicate['op'](m1, m2):
            return False
    return True


def create_filter(filters):
    if not filters:
        return lambda a_dict: True
    predicates = []
    for f in filters.replace(' ', '').split(','):
        predicate = {}
        match = re.split('(!?[^><!=]+)(?:(>=|<=|!=|=|<|>)(.*))?', f, 2)
        predicate['path'] = match[1]
        if match[2]:
            predicate['op'] = get_operator(match[2])
            predicate['value'] = match[3]
        else:
            # predicate with not operator/value means "fields exists"
            if predicate['path'][0] == '!':
                predicate['path'] = predicate['path'][1:]
                predicate['op'] = operator.is_
            else:
                predicate['op'] = operator.is_not
            predicate['value'] = None
        predicates.append(predicate)
    return lambda the_dict: match_predicates(predicates, the_dict)

class ColorizingStreamHandler(logging.StreamHandler):
    """Provide a nicer logging output to error output with colors"""
    colors    = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white']
    color_map = dict([(x, colors.index(x)) for x in colors])
    level_map = {
        logging.DEBUG:    (None,  'blue',   " DBG"),
        logging.INFO:     (None,  'green',  "INFO"),
        logging.WARNING:  (None,  'yellow', "WARN"),
        logging.ERROR:    (None,  'red',    " ERR"),
        logging.CRITICAL: ('red', 'white',  "CRIT")
        }
    csi = '\x1b['
    reset = '\x1b[0m'

    @property
    def is_tty(self):
        isatty = getattr(self.stream, 'isatty', None)
        return isatty and isatty()

    def colorize(self, message, record):
        if record.levelno in self.level_map:
            params = []
            if bg in self.color_map:
                params.append(str(self.color_map[bg] + 40))
            if fg in self.color_map:
                params.append(str(self.color_map[fg] + 30))
            if bold:
                params.append('1')
            if params:
                message = ''.join((self.csi, ';'.join(params),
                                   'm', message, self.reset))
        return message

    def format(self, record):
        message = logging.StreamHandler.format(self, record)
        # Build the prefix
        params = []
        levelno = record.levelno
        if levelno not in self.level_map:
            levelno = logging.WARNING
        bg, fg, level  = self.level_map[levelno]
        if bg in self.color_map:
            params.append(str(self.color_map[bg] + 40))
        if fg in self.color_map:
            params.append(str(self.color_map[fg] + 30))
        params.append("1m")
        level = "[%s]" % level

        return "\n".join(["%s %s: %s" % (
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                    self.is_tty and params and ''.join((self.csi, ';'.join(params),
                                                        level, self.reset)) or level,
                    line)
                          for line in message.split('\n')])
