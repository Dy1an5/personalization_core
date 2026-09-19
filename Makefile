.PHONY: check fix test-matrix build release-check

fix: 
	uv run ruff format .
	uv run ruff check --fix .


check:
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	uv run pytest -m unit


test-matrix:
	uv run pytest -m "unit or contract or integration or e2e"


build:
	uv build


release-check: check test-matrix build
	uv run python scripts/release_smoke.py
