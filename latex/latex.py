# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""Routines for preparing and compiling a LaTeX book."""

# Import standard libraries
from math import floor, ceil
from pathlib import Path
import logging
import re
import subprocess

# Import external libraries
from PIL import Image, ImageOps
from mako.template import Template
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.dollarmath import dollarmath_plugin

# Define constants
SUPERSCRIPTS = '¹|²|³|⁴|⁵|⁶|⁷|⁸|⁹'
BUILD = Path('build')
md = MarkdownIt('commonmark').use(dollarmath_plugin)

# Initialize a logger
LOGGER = logging.getLogger(__name__)


def render_book(book, template):
    """Render a book in LaTeX."""
    with open(template, 'rt') as file:
        template = file.read()
    with open(BUILD/'book.tex', 'wt') as file:
        file.write(Template(template).render(book=book))
    for chapter in book['content']:
        render_chapter(chapter)

    # Run compilation
    rslt = subprocess.run(['latexmk', '-pdf', 'book.tex'], capture_output=True, cwd=BUILD)
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
            file.write(figure['table'])
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
    match obj:
        case SyntaxTreeNode(type='softbreak'):
            return ' '
        case SyntaxTreeNode(type='text'):
            return obj.content
        case SyntaxTreeNode(type='math_inline'):
            formula = obj.content
            formula = formula.replace('\n', ' ')
            formula = re.sub("(?<![a-zA-Z])'(.+?)'", r"\\ltq{}\1\\rtq{}", formula)  # single quotes
            formula = re.sub('"(.+?)"', r"\\ltq{}\1\\rtq{}", formula)  # double quotes
            formula = '$' + formula + '$'
            if len(obj.parent.children) == 1:  # display formula
                formula = '$' + formula + '$'
            return '\0' + formula + '\0'  # \0 markup skips normalization later-on
        case SyntaxTreeNode(type='code_inline'):
            code = obj.content.replace('{', r'\{').replace('}', r'\}')  # escape curly brackets
            code = code.replace(' ', r'\ ')  # fixed-width space
            code = re.sub("(?<![a-zA-Z])'(.+?)'", "`\\1'", code)  # single-quotes
            code = re.sub('"(.+?)"', "`\\1'", code)  # double quotes
            return '\0\\texttt{' + code + '}\0'  # \0 markup skips normalization later-on
        case SyntaxTreeNode(type='paragraph'):
            return md2tex(obj.children) + '\n\n'
        case SyntaxTreeNode(type='em'):
            return r'\emph{' + md2tex(obj.children) + '}'
        case SyntaxTreeNode(type='strong'):
            return r'\textbf{' + md2tex(obj.children) + '}'
        case SyntaxTreeNode(type='ordered_list'):
            return '\\begin{enumerate}\n\n' + md2tex(obj.children) + '\\end{enumerate}\n\n'
        case SyntaxTreeNode(type='bullet_list'):
            return '\\begin{itemize}\n\n' + md2tex(obj.children) + '\\end{itemize}\n\n'
        case SyntaxTreeNode(type='list_item'):
            return '\\item ' + md2tex(obj.children)
        case SyntaxTreeNode():
            return md2tex(obj.children)
        case list():
            return ''.join(md2tex(v) for v in obj)
        case _:
            return ''


def normalize(text):
    """Normalize typography in a LaTeX fragment."""
    return re.sub('(\0.+?\0)|(.+?)(?=$|\0)', normalize_span, text, flags=re.S)


def normalize_span(match):
    """Normalize typography in a span depending on its type."""
    match match.groups():
        case (fixed, None):
            return fixed[1:-1]  # strips \0
        case (None, text):
            text = text.replace('—', '---')  # em dash
            text = re.sub("(?<![a-zA-Z])'(.+?)'", "``\\1''", text)  # single quotes
            text = re.sub('"(.+?)"', "``\\1''", text)  # double quotes
            return text


def detect_footnotes(text):
    """Identify footnotes, format as LaTeX."""
    footnotes = {}

    def fnmark(match):
        return r'\footnote{' + footnotes[match.group(0)] + '}'

    def fntext(match):
        footnotes[match.group(1)] = match.group(2)
        return ''

    text = re.sub(f'^({SUPERSCRIPTS}) *(.*)', fntext, text, flags=re.M)
    return re.sub(SUPERSCRIPTS, fnmark, text)
