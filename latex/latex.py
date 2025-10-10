# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""Routines for preparing and compiling a LaTeX book."""

# Import standard libraries
from math import floor, ceil
from pathlib import Path
import logging
import re
import subprocess
import unittest

# Import external libraries
from PIL import Image, ImageOps
from mako.template import Template
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin

# Import local libraries
from .unicode import VARIABLES, UNICODE

# Define constants
SUPERSCRIPTS = '¹|²|³|⁴|⁵|⁶|⁷|⁸|⁹'
VARIABLES_KEYS = '|'.join(VARIABLES.keys())
UNICODE_KEYS = '|'.join(UNICODE.keys())
BUILD = Path('build')
md = MarkdownIt('commonmark').use(dollarmath_plugin).use(footnote_plugin)

# Initialize a logger
LOGGER = logging.getLogger('latex')


def render_book(book, template):
    """Render a book in LaTeX."""
    with open(template, 'rt') as file:
        template = file.read()
    with open(BUILD/'book.tex', 'wt') as file:
        file.write(Template(template).render(book=book))
    for chapter in book['content']:
        render_chapter(chapter)

    # Run compilation
    rslt = subprocess.run(['latexmk', '-pdf', '-latexoption=-interaction=nonstopmode', 'book.tex'], capture_output=True, cwd=BUILD)
    if rslt.returncode != 0:
        raise RuntimeError('external call to latexmk failed')
    LOGGER.info(f'compiled {BUILD/"book.pdf"}')


def render_chapter(chapter):
    """Render a book chapter in LaTeX."""
    with open(BUILD/f'headpiece-{chapter["number"]}.png', 'wb') as file:
        file.write(chapter['headpiece'])
    with open(BUILD/f'chapter-{chapter["number"]}.tex', 'wt') as file:
        file.write(r'\chapter{%s}' % chapter['title'] + '\n')
        file.write(r'\begin{center}\includegraphics[width=120mm]{headpiece-%d.png}\end{center}' % chapter['number'] + '\n')
        file.write(r'\newpage' + '\n')
        for chunk in chapter['content']:
            render_chunk(file, chunk)
    LOGGER.info(f'rendered chapter-{chapter["number"]}.tex')


def render_chunk(file, chunk):
    """Render a chunk of Markdown in LaTeX; add figures if any."""
    tree = SyntaxTreeNode(md.parse(chunk['chunk']))
    text = detect_footnotes(normalize(md2tex(tree)))
    if 'figure' in chunk:
        figure = chunk['figure']
        ref = 'fig:' + figure['number']
        old_lbl = 'Fig. ' + figure['number']
        new_lbl = r'Fig.~\ref{' + ref + '}'
        caption = re.sub(f'^{old_lbl}(:|.) *', '', figure['caption'])
        caption = caption.replace('\n', ' ')
        caption = normalize(caption)

        text = text.replace(old_lbl, new_lbl)
        paras = (p for p in text.split('\n\n'))

        # Output all the paragrapsh before the first figure mention
        while (par := next(paras)).find(new_lbl) == -1:
            file.write(par)
            file.write('\n\n')

        # Output the figure
        file.write(r'\begin{figure}' + '\n')
        file.write(r'\makebox[\textwidth][c]{' + '\n')

        if figure['type'] == 'Table':
            latex = normalize_quotes(figure['table'], 'table')
            file.write(latex)
        else:
            svg_path = Path(BUILD/f'fig-{figure["number"]}.svg')
            with open(svg_path, 'wt') as svg:
                svg.write(figure['svg'])
            pdf_path = svg2pdf(svg_path)
            x0, x1, y0, y1 = svgbb(svg_path)
            opts = f'bb = {x0} {y0} {x1} {y1}'
            opts += ',width=200mm,height=80mm,keepaspectratio,clip'
            file.write(r'\includegraphics[%s]{%s}' % (opts, pdf_path.relative_to(BUILD)))

        file.write('}\n')
        file.write(r'\caption{%s}' % caption + '\n')
        file.write(r'\label{%s}' % ref + '\n')
        file.write(r'\end{figure}')

        # Output all the remaining paragraphs
        file.write('\n\n')
        file.write(par)
        for par in paras:
            file.write('\n\n')
            file.write(par)
    else:
        file.write(text)


def svgbb(path):
    """Get the bounding box for an SVG (assuming white background).

    An LLM might add white layers here and there, so a simple bounding box
    around all SVG elements does not work for trimming. A simple and robust
    solution is to render SVG and use the raster image to detect the bounding
    box.
    ."""
    png_path = path.with_suffix('.png')
    rslt = subprocess.run(['inkscape', path, '-Do', png_path], capture_output=True)
    if rslt.returncode != 0:
        raise RuntimeError('external call to inkscape failed')
    png = Image.open(png_path)
    _, h = png.size
    x0, y0, x1, y1 = ImageOps.invert(png.convert('RGB')).getbbox()
    y0, y1 = h - y1, h - y0
    s = 72/96  # Inkscape and graphicx use different default units
    return int(floor(s*x0)), int(ceil(s*x1)), int(floor(s*y0)), int(ceil(s*y1))


def svg2pdf(path):
    """Convert SVG to PDF using Inkscape."""
    pdf_path = path.with_suffix('.pdf')
    rslt = subprocess.run(['inkscape', path, '-Do', pdf_path], capture_output=True)
    if rslt.returncode != 0:
        raise RuntimeError('external call to inkscape failed')
    return pdf_path


# Provided conversion rules are ad hoc. There are certain edge cases that won't
# be handled properly. Ideally, I'd draft a specification for a subset of
# Markdown I need, then pass that specification along to an LLM. Then the
# response can be validated against a strict spec and bounced back if the
# validation fails. For now, going a quicker but a less robust route.

def md2tex(obj):
    """Covert a parsed Markdown to LaTeX."""
    footnotes = {}

    def convert(obj):
        # '\0' markup in fomulas and code blocks guards against post-processing
        match obj:
            case SyntaxTreeNode(type='softbreak'):
                return ' '
            case SyntaxTreeNode(type='text'):
                return obj.content
            case SyntaxTreeNode(type='math_inline'):
                formula = obj.content
                formula = formula.replace('\n', ' ')
                formula = normalize_quotes(formula, 'formula')
                formula = '$' + formula + '$'
                if len(obj.parent.children) == 1:  # display formula
                    formula = '$' + formula + '$'
                return '\0' + formula + '\0'
            case SyntaxTreeNode(type='math_block'):
                formula = obj.content.strip()
                formula = normalize_quotes(formula, 'formula')
                if formula.find('\n') == -1:
                    formula = '$$' + formula + '$$'
                else:
                    formula = '$$\n' + formula + '\n$$'
                return '\0' + formula + '\0\n\n'
            case SyntaxTreeNode(type='code_inline'):
                code = obj.content
                sep = find_delimiter(code)
                return f'\0\\Verb{sep}' + code + f'{sep}\0'
            case SyntaxTreeNode(type='paragraph'):
                return convert(obj.children) + '\n\n'
            case SyntaxTreeNode(type='em'):
                return r'\emph{' + convert(obj.children) + '}'
            case SyntaxTreeNode(type='strong'):
                return r'\textbf{' + convert(obj.children) + '}'
            case SyntaxTreeNode(type='ordered_list'):
                return '\\begin{enumerate}\n\n' + convert(obj.children) + '\\end{enumerate}\n\n'
            case SyntaxTreeNode(type='bullet_list'):
                return '\\begin{itemize}\n\n' + convert(obj.children) + '\\end{itemize}\n\n'
            case SyntaxTreeNode(type='list_item'):
                return '\\item ' + convert(obj.children)
            case SyntaxTreeNode(type='footnote_ref'):
                return '\\footnote{%s}' % obj.meta['label']
            case SyntaxTreeNode(type='footnote'):
                footnotes[obj.meta['label']] = convert(obj.children).strip()
                return ''
            case SyntaxTreeNode():
                return convert(obj.children)
            case list():
                return ''.join(convert(v) for v in obj)
            case _:
                return ''

    text = convert(obj)

    # Postprocessing for footnotes
    text = re.sub(r'\\footnote\{(.*?)\}', lambda m: r'\footnote{%s}' % footnotes[m.group(1)], text)

    return text


def normalize(text):
    """Normalize typography in a LaTeX fragment."""
    return re.sub('(\0.+?\0)|(.+?)(?=$|\0)', normalize_span, text, flags=re.S)


def normalize_span(match):
    """Normalize typography in a span depending on its type."""
    match match.groups():
        case (fixed, None):
            # Formula or verbatim
            return fixed[1:-1]  # strips \0
        case (None, text):
            # Text
            text = text.replace('—', '---')  # em dash
            text = normalize_math(text)
            text = normalize_unicode(text)
            text = normalize_quotes(text, 'text')
            # Unescape erroneously escaped asterisks (a known issue with the caching pipeline)
            text = re.sub(r'(?<!\\)\\\*', r'*', text)
            return text


def normalize_quotes(text, context):
    """Normalize quote usage depending on context."""
    match context:
        case 'text':
            text = re.sub("(?<![a-zA-Z}])'(.*?)'", "``\\1''", text)  # single quotes
            text = re.sub('"(.*?)"', "``\\1''", text)  # double quotes
        case 'formula':
            text = re.sub("(?<![a-zA-Z}])'([^`]+?)'", r"\\ltq{}\1\\rtq{}", text)  # single quotes
            text = re.sub("`([^']+?)`", r"\\ltq{}\1\\rtq{}", text)  # backquotes
            text = re.sub('"(.*?)"', r"\\ltq{}\1\\rtq{}", text)  # double quotes
        case 'table':
            text = re.sub("(?<![a-zA-Z}])'([^`]+?)'", r"``\1''", text)  # single quotes
            text = re.sub("`([^']+?)`", r"``\1''", text)  # backquotes
            text = re.sub('"(.*?)"', r"``\1''", text)  # double quotes

    return text


class TestQuoteNormalization(unittest.TestCase):
    """Test quote normalization (and its interaction with Mardkown parsing.)"""

    cases = {
        'text': [
            ('(e.g., "", "ab", "abab")',
             "(e.g., ``'', ``ab'', ``abab'')"),
            ("uncertainty doesn't come",
             "uncertainty doesn't come"),
            (r"the number of \emph{a}'s to ensure an equal number of \emph{b}'s",
             r"the number of \emph{a}'s to ensure an equal number of \emph{b}'s"),
        ],
        'formula': [
            (r"vector('king') - vector('man')",
             r"vector(\ltq{}king\rtq{}) - vector(\ltq{}man\rtq{})"),
        ],
        'table': [
            ("Identify ``Ada Lovelace'' (Person) and ``Google'' (Organization)",
             "Identify ``Ada Lovelace'' (Person) and ``Google'' (Organization)"),
            (r'\texttt{gray|grey} matches "gray" or "grey"',
             r"\texttt{gray|grey} matches ``gray'' or ``grey''"),
        ],
    }

    def test_cases(self):
        for context, subcases in self.cases.items():
            for old, new in subcases:
                self.assertEqual(normalize_quotes(old, context), new)


def normalize_math(text):
    """Recode 'residual' Unicode math to LaTeX."""
    text = re.sub(f'\\b([a-zA-Z]|{VARIABLES_KEYS})(₀|₁|₂|₃|₄|₅|₆|₇|₈|₉)', normalize_subscript, text)
    text = re.sub(f'\\b({VARIABLES_KEYS})\\b', lambda m: '$%s$' % VARIABLES[m.group(1)], text)
    return text


def normalize_subscript(match):
    """Recode 'x₀' and such to LaTeX."""
    var, index = match.groups()
    var = VARIABLES.get(var, var)  # Recode Unicode symbols
    return f'${var}_{ord(index) - 0x2080}$'


def normalize_unicode(text):
    """Recode miscellaneous Unicode to LaTeX."""
    text = re.sub(f'{UNICODE_KEYS}', lambda m: '%s{}' % UNICODE[m.group(0)], text)
    return text


def detect_footnotes(text):
    """Identify non-Markdown footnotes, format as LaTeX."""
    footnotes = {}

    def fnmark(match):
        return r'\footnote{' + footnotes[match.group(0)] + '}'

    def fntext(match):
        footnotes[match.group(1)] = match.group(2)
        return ''

    text = re.sub(f'^({SUPERSCRIPTS}) *(.*)', fntext, text, flags=re.M)
    return re.sub(SUPERSCRIPTS, fnmark, text)


def find_delimiter(code):
    """Find a delimiter not present in the code."""
    for i in range(0x21, 0x7f):  # printable ASCII
        c = chr(i)
        if code.find(c) == -1:
            return c
    else:
        raise RuntimeError('no suitable delimiter found')
