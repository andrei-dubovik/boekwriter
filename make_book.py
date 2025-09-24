# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""Book building logic."""

# Import standard libraries
import argparse
from itertools import count

# Visual features
VISUALS = [
    'Diagram',
    'Chart',
    'Map',
    'Timeline',
    'Illustration',
]

def make_book(model, book, word_count):
    """Use an LLM to write a textbook."""
    # Initialize a global figure counter
    fig = count(1)

    # Draft a list of chapters
    chapters = model.query(
        'chapters',
        validators = [chk_sum('word_count', word_count)],
        slot = 'root',
        book = book,
        word_count = word_count,
    )

    # Focus on the first chapter
    chapter = chapters[0]

    # Draft a chapter outline
    outline = model.query(
        'chapter-outline',
        slot = '0',
        validators = [chk_sum('word_count', chapter['word_count'])],
        book = book,
        chapters = chapters,
        cid = 0,
        word_count = chapter['word_count'],
    )

    # Decide on visual aids (or a table, which is always allowed)
    visuals = model.query(
        'visuals',
        slot = '0',
        validators = [chk_range('number', 1, len(outline))],
        book = book,
        chapter = chapter,
        outline = outline,
        visuals = VISUALS,
    )
    visuals = {v['number'] - 1: v | {'fig': next(fig)} for v in visuals}


if __name__ == '__main__':
    # Parse arguments
    parser = argparse.ArgumentParser(description='Textbook Builder')
    parser.add_argument(
        '--key',
        required = True,
        help = 'API-key file location',
    )
    parser.add_argument(
        '--title',
        required = True,
        help = 'book title',
    )
    parser.add_argument(
        '--words',
        type = int,
        required = True,
        help = 'total word count',
    )
    parser.add_argument(
        '--model',
        default = 'gemini-2.5-pro',
        help = 'LLM model (default: gemini-2.5-pro)',
    )
    args = parser.parse_args()

    # Import standard libraries
    from pathlib import Path

    # Import local libraries
    from llmwrapper.wrapper import Gemini
    from llmwrapper.wrapper import chk_sum, chk_range

    # Initialize an LLM wrapper
    with open(args.key) as file:
        key = file.read().rstrip()

    model = Gemini(
        queries = Path('queries.yaml'),
        cache = Path('cache'),
        key = key,
        model = args.model,
    )

    # Round and round she goes
    make_book(model, book=args.title, word_count=args.words)
