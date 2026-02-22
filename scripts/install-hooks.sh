#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1"
    exit 1
  fi
}

require_cmd git
require_cmd awk
require_cmd mktemp
require_cmd cmp
require_cmd tail

shopt -s nullglob
HOOK_FILES=(.githooks/*)
if [ "${#HOOK_FILES[@]}" -eq 0 ]; then
  echo "No hooks found in .githooks/"
  exit 1
fi

for hook in "${HOOK_FILES[@]}"; do
  if [ -f "$hook" ]; then
    chmod +x "$hook"
  fi
done

git config core.hooksPath .githooks

echo "Installed git hooks using core.hooksPath=.githooks"
echo "Active hooks:"
for hook in "${HOOK_FILES[@]}"; do
  if [ -f "$hook" ]; then
    echo "- $(basename "$hook")"
  fi
done
