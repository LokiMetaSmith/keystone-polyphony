#!/usr/bin/env bash
set -uo pipefail

# Keystone Polyphony - Linting Script
#
# This script runs static analysis checks:
# 1. Python formatting (black)
# 2. Python linting (flake8)
# 3. JavaScript syntax (node -c)
# 4. Shell script syntax (bash -n)

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FAILED=0

echo ">>> Running lint checks..."

# 1. Python Formatting (Black)
if command -v black >/dev/null 2>&1; then
    echo "Checking Python formatting..."
    if ! black . --check --quiet; then
        echo "[ERROR] Python formatting issues found."
        echo "        Run 'black .' to fix them."
        FAILED=1
    fi
else
    echo "[WARNING] 'black' not found. Skipping Python formatting check."
fi

# 2. Python Linting (Flake8)
if command -v flake8 >/dev/null 2>&1; then
    echo "Checking Python linting..."
    if ! flake8 .; then
        echo "[ERROR] Python linting issues found."
        FAILED=1
    fi
else
    echo "[WARNING] 'flake8' not found. Skipping Python linting check."
fi

# 3. JavaScript Syntax
if command -v node >/dev/null 2>&1; then
    echo "Checking JavaScript syntax..."
    while IFS= read -r -d '' file; do
        if ! node -c "$file"; then
            echo "[ERROR] JavaScript syntax error in $file"
            FAILED=1
        fi
    done < <(find . -name "*.js" -not -path "*/node_modules/*" -not -path "*/.*" -print0)
else
    echo "[WARNING] 'node' not found. Skipping JavaScript syntax check."
fi

# 4. Shell Syntax
echo "Checking Shell script syntax..."
while IFS= read -r -d '' file; do
    if ! bash -n "$file"; then
        echo "[ERROR] Shell syntax error in $file"
        FAILED=1
    fi
done < <(find . \( -name "*.sh" -o -path "./.githooks/*" \) -not -path "*/.*" -type f -print0)

if [ "$FAILED" -eq 1 ]; then
    echo ">>> Linting failed."
    exit 1
fi

echo ">>> Linting passed."
exit 0
