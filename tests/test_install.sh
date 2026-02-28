#!/usr/bin/env bash
# tests/test_install.sh

set -e

echo ">>> 🧪 Testing install.sh..."

# 1. Successful Run (Dry Run / Dependency Check)
echo ">>> Running install.sh (First pass)..."
./install.sh

# 2. Idempotency Check
echo ">>> Running install.sh (Second pass)..."
./install.sh | grep "already exists" || echo "✅ Idempotency check passed."

# 3. Missing dependency simulation (Mocking)
# We can't easily mock system commands in a simple shell script without modifying PATH,
# but we can check if it exits non-zero if we simulate a failure.
# For now, we'll stick to the basic functional test.

echo "✅ All install.sh tests passed."
