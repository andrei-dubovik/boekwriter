# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""Miscellaneous utilities."""

# Import standard libraries
from enum import Enum
from hashlib import sha256
from struct import pack
import re

# Import external libraries
from lxml import etree
import mdformat


def deephash(obj):
    """Compute a custom deep hash of an object."""
    msg = sha256()

    def update(obj):
        msg.update(type(obj).__name__.encode())
        match obj:
            case None:
                pass
            case bool(value):
                msg.update(pack('?', value))
            case int(value):
                msg.update(pack('>q', value))
            case str(value):
                msg.update(value.encode())
            case [*args]:
                for arg in args:
                    update(arg)
            case {**kwargs}:
                for k, v in sorted(kwargs.items()):
                    update(k)
                    update(v)
            case _:
                raise RuntimeError('unsupported type')

    update(obj)
    return msg.hexdigest()


def reflow(obj, width=80):
    """Recursively wrap all (markdown) strings at width 80; beautify SVG."""
    match obj:
        case list():
            return [reflow(v, width) for v in obj]
        case dict():
            return {k: reflow(v, width) for k, v in obj.items()}
        case str():
            if obj.startswith('<svg '):
                parser = etree.XMLParser()
                svg = etree.fromstring(obj, parser)
                return etree.tostring(svg, pretty_print=True).decode().rstrip()
            return mdformat.text(obj, options={'wrap': width, 'number': True}).rstrip()
        case _:
            return obj


def upcast(obj):
    """Recursively convert objects to base classes."""
    match obj:
        case None:
            return None
        case Enum():
            return obj.name
        case str():
            return obj
        case int():
            return obj
        case list():
            return [upcast(v) for v in obj]
        case dict():
            return {k: upcast(v) for k, v in obj.items() if v is not None}
        case object(__dict__=fields):
            return {k: upcast(v) for k, v in fields.items() if v is not None}
        case _:
            raise RuntimeError('unsupported type')


COUNT_WORDS = re.compile(r'\W+')

def count_words(txt):
    """Count words in a piece of text."""
    return len(COUNT_WORDS.split(txt.rstrip('.?')))
