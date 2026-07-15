all: check types

check:
	uv run ruff check --output-format=concise

format:
	uv run ruff format

types:
	uv run pyrefly check

# Sync .venv with the locked deps and an editable install of quixote.
setup:
	uv sync

test: setup
	uv run pytest

.PHONY: all check format types setup test
