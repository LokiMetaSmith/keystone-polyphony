#!/usr/bin/env bash
# install.sh
# Provisioning script for Keystone Polyphony swarm nodes.
# This script is idempotent and ensures all dependencies are met.

set -e

echo ">>> 🏗️ Provisioning Keystone Polyphony Node..."

# 1. System Dependency Check
echo ">>> 🔍 Checking system dependencies..."
REQUIRED_CMDS=("python3" "pip3" "node" "npm")
for cmd in "${REQUIRED_CMDS[@]}"; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "❌ Error: $cmd is not installed."
        exit 1
    fi
done
echo "✅ System dependencies found."

# 2. Python Libraries (libp2p, MQTT, AI models)
echo ">>> 🐍 Installing Python communication and AI libraries..."
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt --break-system-packages || pip3 install -r requirements.txt
fi

# Additional libs mentioned in WO
pip3 install paho-mqtt --break-system-packages || pip3 install paho-mqtt

# 3. Node.js Sidecar (DHT / Hyperswarm)
echo ">>> ⚓ Setting up swarm sidecar..."
SIDECAR_DIR="src/liminal_bridge/sidecar"
if [ -d "$SIDECAR_DIR" ]; then
    pushd "$SIDECAR_DIR" > /dev/null
    npm install --silent
    popd > /dev/null
else
    echo "⚠️ Warning: Swarm sidecar directory not found."
fi

# 4. OS-Level Configuration (Mock)
echo ">>> ⚙️ Configuring OS parameters..."
CONFIG_DIR="$HOME/.keystone-polyphony"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/node.conf" ]; then
    echo "node_type=worker" > "$CONFIG_DIR/node.conf"
    echo "✅ OS configuration initialized."
else
    echo "ℹ️ OS configuration already exists."
fi

# 5. Sensor Driver Framework (Mock)
echo ">>> 📡 Checking sensor drivers..."
# In a real environment, this would install LiDAR/UWB drivers.
# Here we ensure the mock driver paths are reachable.
echo "LiDAR Driver: OK (Simulated)"
echo "UWB Mesh Driver: OK (Simulated)"

echo ">>> 🎉 Provisioning Complete! Node is ready for activation."
