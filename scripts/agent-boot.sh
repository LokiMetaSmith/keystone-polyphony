#!/bin/bash
set -e

echo ">>> 🤖 Initializing Agentic Workspace Boot Sequence..."

export HEADLESS=1

# 1. Run standard ensemble setup
./scripts/setup-ensemble.sh

# 2. Launch the Liminal Bridge silently in the background
echo ">>> 🌉 Starting Liminal Bridge in Seed mode..."
python3 src/liminal_bridge/server.py --mode=seed > server.log 2>&1 &

echo ">>> ✅ Agent boot sequence complete. Bridge is backgrounded."
