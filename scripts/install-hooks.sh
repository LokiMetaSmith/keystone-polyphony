#!/usr/bin/env bash
set -euo pipefail

# Keystone Polyphony - Git Hooks Installer
#
# This script configures the local repository to use the hooks
# defined in the .githooks/ directory.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] Missing required command: $1"
    exit 1
  fi
}

# Ensure prerequisites are met
require_cmd git
require_cmd awk
require_cmd mktemp
require_cmd cmp
require_cmd tail

shopt -s nullglob
HOOK_FILES=(.githooks/*)
if [ "${#HOOK_FILES[@]}" -eq 0 ]; then
  echo "[ERROR] No hooks found in .githooks/"
  exit 1
fi

echo ">>> Configuring git hooks..."

# Ensure all hooks are executable
for hook in "${HOOK_FILES[@]}"; do
  if [ -f "$hook" ]; then
    chmod +x "$hook"
  fi
done

# Set core.hooksPath to the version-controlled directory
git config core.hooksPath .githooks

echo ">>> SUCCESS: Git hooks installed."
echo "Active hooks:"
for hook in "${HOOK_FILES[@]}"; do
  if [ -f "$hook" ]; then
    echo "  - $(basename "$hook")"
  fi
done
