# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""A simplified grammar for JSON schemas."""

# Import standard libraries
import ast

# Error definitions
class SchemaError(RuntimeError):
    pass


def load(schema):
    """Make a JSON Schema from a simplified grammar."""

    def convert(tree):
        match tree:
            case ast.List(elts):
                return {
                    'type': 'array',
                    'items': convert(elts[0]),
                }
            case ast.Dict(keys, values):
                return {
                    'type': 'object',
                    'properties': {k.id: convert(v) for k, v in zip(keys, values)},
                    'additionalProperties': False,
                }
            case ast.BinOp(left, _, right):
                return {
                    'type': 'string',
                    'enum': convert(left)['enum'] + convert(right)['enum'],
                }
            case ast.Name(id='ms'):
                return {
                    'type': 'integer',
                    'unit': 'ms',
                }
            case ast.Name(id='int'):
                return {'type': 'integer'}
            case ast.Name(id='png'):
                return {
                    'type': 'string',
                    'mimeType': 'image/png',
                }
            case ast.Name(id='str'):
                return {'type': 'string'}
            case ast.Name(id='json'):
                return True
            case ast.Constant(id):
                return {
                    'type': 'string',
                    'enum': [id],
                }
            case _:
                raise SchemaError()

    return convert(ast.parse(schema).body[0].value)


def dump(schema):
    """Write JSON schema using simplified grammar."""
    match schema:
        case {'type': 'array', 'items': s}:
            return '[' + dump(s) + ']'
        case {'type': 'object', 'properties': fields}:
            return '{' + ', '.join(k + ': ' + dump(s) for k, s in fields.items()) + '}'
        case {'type': 'integer', 'unit': 'ms'}:
            return 'ms'
        case {'type': 'integer'}:
            return 'int'
        case {'type': 'string', 'mimeType': 'image/png'}:
            return 'png'
        case {'type': 'string', 'enum': options}:
            return ' | '.join('"' + v + '"' for v in options)
        case {'type': 'string'}:
            return 'str'
        case True:
            return 'json'
        case _:
            raise SchemaError()


def deduce(obj):
    """Deduce a JSON schema from an object."""
    match obj:
        case list():
            return {
                'type': 'array',
                'items': deduce(obj[0]),  # same type is assumed
            }
        case dict():
            return {
                'type': 'object',
                'properties': {k: deduce(v) for k, v in obj.items()},
                'additionalProperties': False,
            }
        case int():
            return {'type': 'integer'}
        case str():
            return {'type': 'string'}
        case _:
            raise SchemaError()
