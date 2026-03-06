.PHONY: test lint typecheck build clean link unlink

test:
	uv run pytest

test-quick:
	uv run pytest -x -q

lint:
	uv run ruff check src/

typecheck:
	uv run pyright src/

build:
	uv build

clean:
	rm -rf dist/ build/ *.egg-info

link:
	uv pip install -e ../fcp-core/python

unlink:
	uv pip install fcp-core
