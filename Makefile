all: check types

check:
	uv run ruff check --output-format=concise

format:
	uv run ruff format

types:
	uv run pyrefly check
