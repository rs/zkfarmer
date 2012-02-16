import json
import operator
import logging


def serialize(data):
    try:
        if type(data) != dict:
            raise TypeError('Must be a dict')
        return json.dumps(data)
    except:
        logging.warn('Cannot serialize: %s' % data)
        return '{}'


def unserialize(serialized):
    try:
        data = json.loads(serialized)
        if type(data) != dict:
            raise TypeError('Not a dict')
        return data
    except:
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
