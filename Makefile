.PHONY: clean

build/book.pdf:
	python make_book.py \
	  --key gemini.key \
	  --title "Introduction to Computational Linguistics" \
	  --words 90000

clean:
	rm -f build/book.pdf
