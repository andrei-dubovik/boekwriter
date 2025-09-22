# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""Miscellaneous utilities."""

# Import standard libraries
from hashlib import sha256
from struct import pack
import textwrap


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
    """Recursively wrap all strings at width 80."""
    match obj:
        case list():
            return [reflow(v, width) for v in obj]
        case dict():
            return {k: reflow(v, width) for k, v in obj.items()}
        case str():
            return textwrap.fill(obj, width=width).rstrip()
        case _:
            return obj
