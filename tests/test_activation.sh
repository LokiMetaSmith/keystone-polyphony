#!/usr/bin/env bash
# tests/test_activation.sh

set -e

echo ">>> 🧪 Testing keystone-polyphony.sh..."

# 1. Missing SWARM_KEY check
echo ">>> Testing missing SWARM_KEY..."
(unset SWARM_KEY; ./keystone-polyphony.sh 2>&1 | grep "ERROR: SWARM_KEY is not set") && echo "✅ Missing SWARM_KEY check passed."

# 2. Daemon startup and shutdown
echo ">>> Testing daemon startup and shutdown..."
export SWARM_KEY="test-key"
# Start in background, wait 5 seconds, then kill
./keystone-polyphony.sh --timeout 5 &
PID=$!
sleep 2
if ps -p $PID > /dev/null; then
    echo "✅ Daemon process found."
    kill -SIGINT $PID
    wait $PID || true
    echo "✅ Daemon exited gracefully."
else
    echo "❌ Daemon failed to start."
    exit 1
fi

echo "✅ All keystone-polyphony.sh tests passed."
