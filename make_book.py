# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""Book building logic."""

# Import standard libraries
import argparse

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
    # Draft a list of chapters
    chapters = model.query(
        'chapters',
        validators = [chk_sum('word_count', word_count)],
        slot = 'root',
        book = book,
        word_count = word_count,
    )

    # Write the book
    content = [
        make_chapter(book, chapters, cid)
        for cid in range(len(chapters))
    ]

    return {
        'content': content,
    }


def make_chapter(book, chapters, cid):
    """Draft a single chapter."""
    chapter = chapters[cid]

    # Draft a chapter outline
    outline = model.query(
        'chapter-outline',
        slot = f'{cid+1}',
        validators = [chk_sum('word_count', chapter['word_count'])],
        book = book,
        chapters = chapters,
        cid = cid,
        word_count = chapter['word_count'],
    )

    # Decide on visual aids (or a table, which is always allowed)
    visuals = model.query(
        'visuals',
        slot = f'{cid+1}',
        validators = [chk_range('number', 1, len(outline))],
        book = book,
        chapter = chapter,
        outline = outline,
        visuals = VISUALS,
    )
    visuals = {v['number'] - 1: v | {'fig': f'{cid+1}.{v["number"]}'} for v in visuals}

    # Write the chapter
    content = [
        make_section(book, chapters, cid, outline, oid, visuals)
        for oid in range(len(outline))
    ]

    return chapter | {
        'content': content,
    }


def make_section(book, chapters, cid, outline, oid, visuals):
    """Draft a section of a book."""
    min_words = outline[oid]['word_count']*3//4
    max_words = outline[oid]['word_count']
    visual = visuals.get(oid)

    chunk = model.query(
        'chunk',
        slot = f'{cid+1}-{oid+1}',
        validators = [chk_words(min_words, max_words)],
        book = book,
        chapters = chapters,
        outline = outline,
        cid = cid,
        oid = oid,
        min_words = min_words,
        max_words = max_words,
        visual = visual,
    )

    # Draft a visual aid, if any
    figure = None
    if visual is not None:
        figure = {
            'number': visual['fig'],
            'type': visual['aid'],
        }
        if visual['aid'] == 'Table':
            response = model.query(
                'table',
                slot = f'{cid+1}-{oid+1}',
                validators = [],
                book = book,
                chunk = chunk,
                visual = visual,
            )
            figure['caption'] = response['caption']
            figure['table'] = response['latex']
        else:
            response = model.query(
                'figure',
                slot = f'{cid+1}-{oid+1}',
                validators = [],
                book = book,
                chunk = chunk,
                visual = visual,
            )
            figure['caption'] = response['caption']
            figure['svg'] = response['svg']

    return {'chunk': chunk} | ({} if figure is None else {'figure': figure})


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
    from itertools import count
    from pathlib import Path

    # Import local libraries
    from llmwrapper.wrapper import Gemini
    from llmwrapper.wrapper import chk_sum, chk_range, chk_words

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
    _ = make_book(model, book=args.title, word_count=args.words)
