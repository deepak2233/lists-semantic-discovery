.PHONY: setup run test lint evaluate smoke
setup:
	uv sync --extra dev
	npm ci
run:
	uv run uvicorn lists_api.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
test:
	uv run pytest
	npm test
lint:
	uv run ruff check .
	uv run ruff format --check .
evaluate:
	uv run python scripts/evaluate.py
smoke:
	uv run python scripts/smoke.py
