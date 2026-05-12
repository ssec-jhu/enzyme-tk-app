# Makefile for enzyme-tk-app
# Cleans up generated artifacts and wraps common docker compose workflows.

.PHONY: clean help dev dev-down prod prod-down

help:
	@echo "Available commands:"
	@echo "  make dev        - Start the dev stack (web + redis + worker)"
	@echo "  make dev-down   - Stop the dev stack"
	@echo "  make prod       - Start the prod stack (requires .env.prod)"
	@echo "  make prod-down  - Stop the prod stack"
	@echo "  make clean      - Remove all generated artifacts"

# ---- Docker Compose -------------------------------------------------------
#
# Dev: zero-config; binds the repo's ./data dir read-only into /data.
# Prod: requires .env.prod (see .env.prod.example).  Prints a clear error
#       and exits non-zero if .env.prod is missing.

DEV_COMPOSE  := docker compose -f docker-compose.yml -f docker-compose.dev.yml
PROD_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod

dev:
	$(DEV_COMPOSE) up --build

dev-down:
	$(DEV_COMPOSE) down

prod:
	@test -f .env.prod || (echo "ERROR: .env.prod not found. Copy .env.prod.example and fill it in." && exit 1)
	$(PROD_COMPOSE) up -d --build

prod-down:
	@test -f .env.prod || (echo "ERROR: .env.prod not found." && exit 1)
	$(PROD_COMPOSE) down

# ---- Cleanup --------------------------------------------------------------
# Remove generated artifacts:
#   .tox/           — tox virtualenvs
#   .ruff_cache/    — ruff cache (format, check-style)
#   coverage.xml    — pytest-cov XML report (test)
#   .coverage       — pytest-cov binary data
#   coverage.html/  — pytest-cov HTML report (test)
#   .pytest_cache/  — pytest cache (test)
#   dist/           — built package (build-dist)
#   build/          — intermediate build directory (pip install / python -m build)
#   *.egg-info/     — editable install metadata (pip install -e .)
#   docs/_build/    — Sphinx output (build-docs)
#   __pycache__/    — Python bytecode caches
#   .mypy_cache/    — mypy type checker cache
#   .DS_Store       — macOS Finder metadata
clean:
	rm -rf .tox/
	rm -rf .ruff_cache/
	rm -rf coverage.xml
	rm -rf .coverage
	rm -rf coverage.html/
	rm -rf .pytest_cache/
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	rm -rf enzyme_tk_app.egg-info/
	rm -rf docs/_build/
	rm -rf .mypy_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
	find . -name ".DS_Store" -delete 2>/dev/null || true
	@echo "✓ Cleanup complete"
