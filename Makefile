# Makefile for enzyme-tk-app
# Cleans up generated artifacts.

.PHONY: clean help

help:
	@echo "Available commands:"
	@echo "  make clean  - Remove all generated artifacts"

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

-include .env

deploy-azure:
	@echo "Deploying to Azure..."
	az deployment group create \
	-g enzyme-tk-rg \
	-f main.bicep \
	--parameters \
	ghcrUsername=$(GH_USERNAME) \
	ghcrPat=$(GH_PAT) \
	adminToken=$(ETK_ADMIN_TOKEN) \
	secretKey=$(ETK_SECRET_KEY)

	@echo "Deployment complete."