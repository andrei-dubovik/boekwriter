# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""Miscellaneous utilities."""

# Import standard libraries
from enum import Enum
from hashlib import sha256
from struct import pack
import re

# Import external libraries
from lxml import etree
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
import mdformat


class DollarMath():
    """A basic LaTeX math plugin for mdformat."""
    @staticmethod
    def update_mdit(mdit):
        mdit.use(dollarmath_plugin)

    @staticmethod
    def math_inline(node, context):
        return f'${node.content}$'

    @staticmethod
    def math_block(node, context):
        return f'$${node.content}$$'

    @staticmethod
    def escape_text(text, node, context):
        return text.replace('$', '\\$')

    RENDERERS = {
        'math_inline': math_inline,
        'math_block': math_block,
    }
    POSTPROCESSORS = {'text': escape_text}


class Footnote():
    """A basic footnote plugin for mdformat."""
    @staticmethod
    def update_mdit(mdit):
        mdit.use(footnote_plugin)

    @staticmethod
    def footnote_ref(node, context):
        return f'[^{node.meta["label"]}]'

    @staticmethod
    def footnote_block(node, context):
        return '\n\n'.join(child.render(context) for child in node.children)

    @staticmethod
    def footnote(node, context):
        if len(node.children) > 1:
            # Unlikely an LLM would put several paragraphs in a footnote
            raise RuntimeError('not implemented')
        return f'[^{node.meta["label"]}]: ' + node.children[0].render(context)

    RENDERERS = {
        'footnote_ref': footnote_ref,
        'footnote_block': footnote_block,
        'footnote': footnote,
    }


class Table():
    """A pass-through table plugin for mdformat."""
    @staticmethod
    def update_mdit(mdit):
        mdit.enable('table')

    @staticmethod
    def render_children(node, context):
        return (child.render(context) for child in node.children)

    @staticmethod
    def table(node, context):
        return ''.join(Table.render_children(node, context))

    @staticmethod
    def thead(node, context):
        context.env['columns'] = []
        row = node.children[0].render(context) + '\n'
        row += '| ' + ' | '.join(context.env['columns']) + ' |\n'
        return row

    @staticmethod
    def tbody(node, context):
        return '\n'.join(Table.render_children(node, context))

    @staticmethod
    def tr(node, context):
        cells = [c.strip() for c in Table.render_children(node, context)]
        cells = [' ' + c + ' ' if c != '' else ' ' for c in cells]
        return '|' + '|'.join(cells) + '|'

    @staticmethod
    def th(node, context):
        style = node.attrs.get('style', '')
        if 'text-align:right' in style:
            context.env['columns'].append('---:')
        elif 'text-align:center' in style:
            context.env['columns'].append(':---:')
        else:
            context.env['columns'].append(':---')
        return ''.join(Table.render_children(node, context))

    @staticmethod
    def td(node, context):
        return ''.join(Table.render_children(node, context))

    RENDERERS = {
        'table': table,
        'thead': thead,
        'tbody': tbody,
        'tr': tr,
        'th': th,
        'td': th,
    }


# Enable LaTeX, footnote and table support in mdformat
mdformat.plugins.PARSER_EXTENSIONS['dollarmath'] = DollarMath
mdformat.plugins.PARSER_EXTENSIONS['footnote'] = Footnote
mdformat.plugins.PARSER_EXTENSIONS['table'] = Table


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
            if obj.startswith(r'\begin{'):
                # Do not reflow LaTeX
                return obj
            if obj.startswith('<svg '):
                parser = etree.XMLParser()
                svg = etree.fromstring(obj, parser)
                return etree.tostring(svg, pretty_print=True).decode().rstrip()
            return mdformat.text(
                obj,
                options = {'wrap': width, 'number': True},
                extensions = {'dollarmath', 'footnote', 'table'},
            ).rstrip()
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
