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
    'Photograph',
    'Illustration',
]


def make_book(model, title, word_count):
    """Use an LLM to write a textbook."""
    # Draft a list of chapters
    chapters = model.query(
        'chapters',
        validators = [chk_sum('word_count', word_count)],
        slot = 'root',
        book = title,
        word_count = word_count,
    )

    # Write the book
    content = [
        make_chapter(title, chapters, cid)
        for cid in range(len(chapters))
    ]

    return {
        'title': title,
        'content': content,
        'model': model.model,
        'date': date.today().strftime('%B %Y'),
    }


def make_chapter(title, chapters, cid):
    """Draft a single chapter."""
    chapter = chapters[cid]

    # Draft a chapter outline
    outline = model.query(
        'chapter-outline',
        slot = f'{cid+1}',
        validators = [chk_sum('word_count', chapter['word_count'])],
        book = title,
        chapters = chapters,
        cid = cid,
        word_count = chapter['word_count'],
    )

    # Decide on visual aids (or a table, which is always allowed)
    visuals = model.query(
        'visuals',
        slot = f'{cid+1}',
        validators = [chk_range('number', 1, len(outline))],
        book = title,
        chapter = chapter,
        outline = outline,
        visuals = VISUALS,
    )
    visuals = {v['number'] - 1: v | {'fig': f'{cid+1}.{v["number"]}'} for v in visuals}

    # Write the chapter
    content = [
        make_section(title, chapters, cid, outline, oid, visuals)
        for oid in range(len(outline))
    ]

    # Make a headpiece
    hp_task = model.query(
        'headpiece',
        slot = f'{cid+1}',
        validators = [],
        book = title,
        content = content,
    )

    hp_image = model.query(
        'image',
        slot = f'{cid+1}',
        validators = [],
        prompt = hp_task,
    )

    return chapter | {
        'content': content,
        'headpiece': hp_image,
    }


def make_section(title, chapters, cid, outline, oid, visuals):
    """Draft a section of a book."""
    min_words = outline[oid]['word_count']*3//4
    max_words = outline[oid]['word_count']
    visual = visuals.get(oid)

    chunk = model.query(
        'chunk',
        slot = f'{cid+1}-{oid+1}',
        validators = [chk_words(min_words, max_words)],
        book = title,
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
                book = title,
                chunk = chunk,
                visual = visual,
            )
            figure['caption'] = response['caption']
            figure['table'] = response['latex']
        elif visual['aid'] == 'Photograph':
            # PNG
            response = model.query(
                'image',
                slot = f'{cid+1}-{oid+1}',
                validators = [],
                prompt = visual['description'],
            )
            figure['png'] = response

            # Caption
            #pdb.set_trace()
            response = model.query(
                'photo-caption',
                slot = f'{cid+1}-{oid+1}',
                validators = [],
                chunk = chunk,
                visual = visual,
            )
            figure['caption'] = response['caption']
        else:
            response = model.query(
                'figure',
                slot = f'{cid+1}-{oid+1}',
                validators = [],
                book = title,
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
    parser.add_argument(
        '--template',
        default = 'template.tex',
        help = 'title page LaTeX template (default: template.tex)',
    )
    args = parser.parse_args()

    # Import standard libraries
    from datetime import date
    from itertools import count
    from pathlib import Path
    import logging

    # Import local libraries
    from llmwrapper.wrapper import Gemini
    from llmwrapper.wrapper import chk_sum, chk_range, chk_words
    import latex

    # Configure logging
    logging.basicConfig(
        format = '%(asctime)s [%(name)s:%(levelname)s] %(message)s',
        datefmt = '%Y-%d-%m %H:%M:%S',
        level = logging.INFO,
    )
    logging.getLogger('google_genai.models').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

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
    book = make_book(model, title=args.title, word_count=args.words)
    latex.render_book(book, template=args.template)
