BoekWriter
==========

A collection of generic prompts for writing any given book in a structured manner using an LLM, plus a Python scaffolding for executing those prompts, for caching, and for LaTeX compilation. The LaTeX compilation is somewhat brittle at the moment and is likely to fail for more technical books.

For the story behind this project, take a look at my blog ["Gemini and I Wrote a Book: Introduction to Computational Linguistics"](https://dubovik.eu/blog/computational-linguistics).

## Library

Some pre-compiled books can be found on the project's [releases](https://github.com/andrei-dubovik/boekwriter/releases) page.

## Usage

At the moment, Gemini and Claude models are supported. To generate a book using Gemini Pro, with illustrations by Gemini Flash Image (these are the default settings), run

```bash
python write_book.py --title [BOOK_TITLE] --words [WORD_COUNT] --gemini-key [KEYFILE]
```

The final book is saved as `build/book.pdf`. All prompt-response pairs are cached in `cache`.

## Introduction to Computational Linguistics

The tool has been developed on the aforementioned book title. To compile the book from cached Gemini responses,

```bash
git checkout computational-linguistics-202510
echo 'dummy' > dummy.key
python make_book.py \
  --key dummy.key \
  --title "Introduction to Computational Linguistics" \
  --words 90000
```

## Requirements

- python
  - PIL
  - anthropic
  - google.genai
  - jsonschema
  - lxml
  - mako
  - markdown_it
  - mdformat
  - mdit_py_plugins
- latex
  - latexmk
  - [common packages, see template.tex]
- inkscape
