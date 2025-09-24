# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""A YAML-like data serialization language with explicit schemas."""

# Import standard libraries
import json

# Import external libraries
from jsonschema import validate

# Import local libraries
from . import jsonschema

# Initialization functions for block types
BLOCK_TYPES = {
    'string': bytearray,  # str is immutable
    'array': list,
    'object': dict,
}


# Error definitions
class YAMLError(RuntimeError):
    pass

class ParseError(YAMLError):
    pass

class SerializeError(YAMLError):
    pass

class NotFound(YAMLError):
    pass

class StopInline(YAMLError):
    """No inline type is available."""


def load(file):
    """Load a collection of documents."""
    for line in file:
        if not line.startswith('#'):
            schema = jsonschema.load(line.strip())
            break
    if next(file).rstrip() != '---':
        raise ParseError()
    obj = []
    block = []
    for line in file:
        line = line.rstrip()
        if line == '---' or line == '...':
            block.reverse()
            obj.append(BLOCK_TYPES[schema['type']]())
            parse(block, obj[-1], schema, 0)
        else:
            block.append(line)
    if line != '...':
        raise ParseError()
    return schema, [unwrap(v, schema) for v in obj]


def find(file, **kwargs):
    """Find a specific document in the collection."""
    schema, documents = load(file)
    if schema['type'] != 'object':
        raise NotFound()
    for obj in documents:
        if all(k in obj and obj[k] == v for k, v in kwargs.items()):
            return schema, obj
    raise NotFound()


def parse(lines, obj, schema, level):
    """Recursively parse a YAML-like grammar."""
    while True:
        # Unwind on document end
        if len(lines) == 0:
            return

        # Keep empty lines if parsing a string, skip otherwise
        line = lines.pop()
        if line == '':
            if schema['type'] == 'string':
                obj += '\n'.encode()
            continue

        # Unwind on level decrease
        tabstop = level*2
        indent = len(line) - len(line.lstrip(' '))
        if indent < tabstop:
            lines.append(line)
            return

        # Process the active line according to the active schema
        line = line[tabstop:]
        match schema:
            case {'type': 'string'}:
                obj += (line + '\n').encode()
            case {'type': 'array', 'items': _schema}:
                if not line.startswith('- '):
                    lines.append(' '*tabstop + line)
                    return
                if _schema == True:  # arbitrary JSON
                    _schema = {'type': 'string'}
                _type = _schema['type']
                try:
                    obj.append(parse_inline(line[2:], _schema))
                except StopInline:
                    lines.append(' '*(tabstop + 2) + line[2:])
                    obj.append(BLOCK_TYPES[_type]())
                    parse(lines, obj[-1], _schema, level + 1)
            case {'type': 'object', 'properties': fields}:
                for key, _schema in fields.items():
                    if _schema == True:  # arbitrary JSON
                        _schema = {'type': 'string'}
                    _type = _schema['type']
                    if line.startswith(key + ': '):  # inline data (or string)
                        if _type == 'string':
                            lines.append(' '*(tabstop + 2) + line.removeprefix(key + ': '))
                            line = key + ':'
                        else:
                            obj[key] = parse_inline(line.removeprefix(key + ': '), _schema)
                            break
                    if line == key + ':':  # block data
                        obj[key] = BLOCK_TYPES[_type]()
                        shift = 0 if _type == 'array' else 1  # compact style
                        parse(lines, obj[key], _schema, level + shift)
                        break
                else:
                    raise ParseError()
            case _:
                raise ParseError()


def parse_inline(value, schema):
    """Parse an inline value."""
    match schema:
        case {'type': 'integer', 'unit': unit}:
            if not value.endswith(' ' + unit):
                raise ParseError()
            return int(value[:-(1 + len(unit))])
        case {'type': 'integer'}:
            return int(value)
        case _:
            raise StopInline()


def unwrap(obj, schema):
    """Recursively replace bytearrays with strings, unwrap JSON"""
    match obj:
        case list():
            return [unwrap(v, schema['items']) for v in obj]
        case dict():
            return {k: unwrap(v, schema['properties'][k]) for k, v in obj.items()}
        case bytearray():
            s = obj.decode()[:-1]  # remove '\n'
            if schema == True:
                return json.loads(s)
            else:
                return s
        case _:
            return obj


def dump(schema, documents, file):
    """Serialize a collection of documents."""
    file.write(jsonschema.dump(schema) + '\n')
    for obj in documents:
        validate(obj, schema)
        file.write('---\n')
        serialize(file, wrap(obj, schema), schema, 0)
    file.write('...\n')


def serialize(file, obj, schema, level, hanging=None):
    """Recursively serialize to a YAML-like grammar."""
    tab = '  '*level
    match obj:
        case str():
            for i, line in enumerate(obj.split('\n')):
                pfx = hanging if i == 0 and hanging is not None else tab
                file.write(pfx + line + '\n')
        case list():
            for i, value in enumerate(obj):
                pfx = hanging if i == 0 and hanging is not None else tab
                serialize(file, value, schema['items'], level + 1, pfx + '- ')
        case dict():
            for i, (key, value) in enumerate(obj.items()):
                pfx = hanging if i == 0 and hanging is not None else tab
                _schema = schema['properties'][key]
                try:
                    file.write(pfx + key + ': ' + serialize_inline(value, _schema) + '\n')
                except StopInline:
                    if type(value) == str and value.find('\n') == -1:
                        # Inline style
                        serialize(file, value, _schema, level + 1, pfx + key + ': ')
                    else:
                        # Block style
                        file.write(pfx + key + ':\n')
                        shift = 0 if type(value) == list else 1  # compact style
                        serialize(file, value, _schema, level + shift)
        case _:
            raise SerializeError()


def serialize_inline(obj, schema):
    """Serialzie an inline value."""
    match schema:
        case {'type': 'integer', 'unit': unit}:
            return str(obj) + ' ' + unit
        case {'type': 'integer'}:
            return str(obj)
        case _:
            raise StopInline()


def wrap(obj, schema):
    """Recursively replace arbitrary JSONs with strings."""
    match schema:
        case {'type': 'array', 'items': items}:
            return [wrap(v, items) for v in obj]
        case {'type': 'object', 'properties': fields}:
            return {k: wrap(v, fields[k]) for k, v in obj.items()}
        case True:
            text = json.dumps(obj)
            if len(text) > 80:
                text = json.dumps(obj, indent=2)
            return text
        case _:
            return obj
