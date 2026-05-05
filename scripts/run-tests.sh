#!/usr/bin/env bash
set -euo pipefail

# Keystone Polyphony - Basic Repository Health Checks
# This script is used by both the pre-push hook and CI/CD pipelines.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ">>> Running repository health checks..."


# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    fi
fi

# Detect python executable
if command -v python3 &>/dev/null && python3 -c "import sys" 2>/dev/null; then
    PYTHON_EXEC="python3"
elif command -v python &>/dev/null && python -c "import sys" 2>/dev/null; then
    PYTHON_EXEC="python"
else
    PYTHON_EXEC=""
fi

FAILED=0

# 1. Run Linting (Code Quality)
echo "Running lint checks..."
if ! ./scripts/lint.sh; then
    echo "[ERROR] Linting checks failed."
    FAILED=1
fi

# 2. Run Tests (Unit Tests)
if [ -n "$PYTHON_EXEC" ] && $PYTHON_EXEC -c "import pytest" >/dev/null 2>&1; then
    export PYTHONPATH=src
    echo "Running pytest..."
    if ! $PYTHON_EXEC -m pytest; then
        echo "[ERROR] Unit tests failed."
        FAILED=1
    fi
else
    echo "[WARNING] pytest module not found. Skipping unit tests."
fi

# 3. Check for broken symbolic links (if any)
echo "Checking for broken symbolic links..."
while IFS= read -r -d '' link; do
    if [ ! -e "$link" ]; then
        echo "[ERROR] Broken symbolic link: $link"
        FAILED=1
    fi
done < <(find . -type l -not -path "*/.*" -print0)

if [ $FAILED -eq 0 ]; then
    echo ">>> All checks passed!"
    exit 0
else
    echo ">>> [ERROR] Some checks failed."
    exit 1
fi
