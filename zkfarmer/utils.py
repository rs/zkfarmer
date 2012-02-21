import json
import operator
import logging
import re


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
    if op == '==' or op == '=':
        return operator.eq
    elif op == '!=':
        return operator.ne
    elif op == '>=':
        return operator.ge
    elif op == '<=':
        return operator.le
    elif op == '>':
        return operator.gt
    elif op == '<':
        return operator.lt
    else:
        raise ValueError('Unknown operator: %s' % op)


def match_predicates(predicates, the_dict):
    for predicate in predicates:
        if not predicate['op'](dict_get_path(the_dict, predicate['path']), predicate['value']):
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
