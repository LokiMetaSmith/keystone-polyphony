#!/usr/bin/env bash
set -euo pipefail

# Keystone Polyphony - Basic Repository Health Checks
# This script is used by both the pre-push hook and CI/CD pipelines.

echo ">>> Running repository health checks..."

FAILED=0

# 1. Check shell scripts syntax (including git hooks)
echo "Checking shell scripts syntax..."
while IFS= read -r -d '' file; do
    if ! bash -n "$file"; then
        echo "[ERROR] Shell syntax error in $file"
        FAILED=1
    fi
done < <(find . \( -name "*.sh" -o -path "./.githooks/*" \) -not -path "*/.*" -type f -print0)

# 2. Check for broken symbolic links (if any)
echo "Checking for broken symbolic links..."
while IFS= read -r -d '' link; do
    if [ ! -e "$link" ]; then
        echo "[ERROR] Broken symbolic link: $link"
        FAILED=1
    fi
done < <(find . -type l -not -path "*/.*" -print0)

# 3. Future tests can be added here (e.g. markdown link checking, etc.)

if [ $FAILED -eq 0 ]; then
    echo ">>> All checks passed!"
    exit 0
else
    echo ">>> [ERROR] Some checks failed."
    exit 1
fi
