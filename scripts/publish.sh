#!/bin/bash
# Publish tidewatch to PyPI
# Prerequisites: pip install build twine
# Usage: ./scripts/publish.sh
set -euo pipefail

echo "=== Pre-publish checks ==="
python3 -m pytest tests/ -q --tb=no
python3 -m ruff check tidewatch/ tests/
echo "Tests and lint pass."

echo ""
echo "=== Building ==="
rm -rf dist/ build/
python3 -m build
echo ""

echo "=== Package contents ==="
ls -la dist/
echo ""

echo "=== Upload to PyPI ==="
echo "Run: python3 -m twine upload dist/*"
echo "(Requires PyPI account + API token)"
echo ""
echo "After upload, update README badges with real PyPI version."
