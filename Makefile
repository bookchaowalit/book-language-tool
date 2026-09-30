.PHONY: check test demo typecheck

check:
	PYTHONPATH=src python3 -m book_language_tool.cli check examples/hello.book

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

demo:
	PYTHONPATH=src python3 -m book_language_tool.cli run examples/hello.book

typecheck:
	python3 -m mypy
