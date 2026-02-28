#!/usr/bin/env bash
# keystone-polyphony.sh
# Activation script for Keystone Polyphony swarm nodes.
# This script attaches the node to the autonomous grid.

set -e

# 1. Validation
if [ -z "$SWARM_KEY" ]; then
    echo "❌ ERROR: SWARM_KEY is not set. Please export it before running."
    exit 1
fi

echo ">>> 🐝 Activating Keystone Polyphony Node..."
echo ">>> Topic: $(echo -n $SWARM_KEY | sha256sum | head -c 8)..."

# 2. Execution
# We run the server in 'seed' mode which handles P2P discovery and gossip.
# Standard persistent paths for the daemon.
export LIMINAL_DB="${LIMINAL_DB:-$HOME/.keystone-polyphony/swarm.db}"
export LIMINAL_IDENTITY="${LIMINAL_IDENTITY:-$HOME/.keystone-polyphony/identity.pem}"

# Run the Python daemon
# Note: Use exec to pass signals (SIGINT/SIGTERM) directly to the python process.
exec python3 src/liminal_bridge/server.py --mode seed "$@"
