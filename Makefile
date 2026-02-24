# Makefile for enzyme-tk-app

.PHONY: clean clean-pyc clean-build clean-test clean-all run help

help:
	@echo "Available commands:"
	@echo "  make clean       - Remove all build/cache artifacts"
	@echo "  make clean-pyc   - Remove Python bytecode files"
	@echo "  make clean-build - Remove build artifacts"
	@echo "  make clean-test  - Remove test/coverage artifacts"
	@echo "  make run         - Run the Dash app"

# Remove Python bytecode and __pycache__ directories
clean-pyc:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
	find . -type f -name "*~" -delete 2>/dev/null || true

# Remove build artifacts
clean-build:
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	rm -rf enzyme_tk_app.egg-info/

# Remove test and coverage artifacts
clean-test:
	rm -rf .tox/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf coverage.html/
	rm -rf .pytest_cache/
	rm -rf htmlcov/

# Remove linter/tool caches
clean-cache:
	rm -rf .ruff_cache/
	rm -rf .mypy_cache/
	rm -rf .idea/

# Remove macOS artifacts
clean-macos:
	find . -name ".DS_Store" -delete 2>/dev/null || true

# Remove all artifacts
clean: clean-pyc clean-build clean-test clean-cache clean-macos
	@echo "✓ Cleanup complete"

# Run the Dash application
run:
	cd enzyme_tk_app/app && python app.py
