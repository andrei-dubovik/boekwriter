.PHONY: clean

build/book.pdf:
	python write_book.py \
	  --title "A Tinkerer's Introduction to Claude Code" \
	  --words 16000 \
	  --gemini-key gemini.key \
	  --claude-key claude.key \
	  --text-model claude-opus-4-6

clean:
	rm -f build/book.pdf
