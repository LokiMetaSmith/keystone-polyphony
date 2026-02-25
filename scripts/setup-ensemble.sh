#!/bin/bash
# scripts/setup-ensemble.sh

set -e

echo ">>> 🚀 Initializing Polyphony Ensemble Baseline..."

# 1. Dependency Check
echo ">>> 🔍 Checking system dependencies..."
REQUIRED_CMDS=("python3" "pip3" "node" "npm" "gh" "ssh-keygen")
for cmd in "${REQUIRED_CMDS[@]}"; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "❌ Error: $cmd is not installed."
        if [ "$cmd" == "gh" ]; then
            echo ">>> �️ Attempting to install GitHub CLI (gh)..."
            if command -v apt-get &> /dev/null; then
                sudo apt-get update
                sudo apt-get install -y curl
                curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
                sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
                echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
                sudo apt-get update
                sudo apt-get install -y gh
                echo "✅ gh installed successfully."
            else
                echo "�💡 Hint: Please install GitHub CLI manually via: https://cli.github.com/manual/installation"
                exit 1
            fi
        else
            echo "💡 Hint: Please install $cmd using your package manager."
            exit 1
        fi
    fi
done
echo "✅ System dependencies found."

# 2. Python Dependencies
echo ">>> 🐍 Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt
else
    echo "⚠️ Warning: requirements.txt not found."
fi

# 3. Node.js Sidecar Dependencies
echo ">>> ⚓ Installing Swarm Sidecar dependencies..."
SIDECAR_DIR="src/liminal_bridge/sidecar"
if [ -d "$SIDECAR_DIR" ]; then
    pushd "$SIDECAR_DIR" > /dev/null
    npm install
    popd > /dev/null
else
    echo "⚠️ Warning: Swarm sidecar directory not found at $SIDECAR_DIR"
fi

# 4. SSH Key Management
SSH_DIR="$HOME/.ssh"
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"

SSH_KEY="$SSH_DIR/id_ed25519"
if [ ! -f "$SSH_KEY" ]; then
    echo ">>> 🔑 Generating new SSH key..."
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N ""
    echo "✅ SSH key generated at $SSH_KEY"
else
    echo "ℹ️ SSH key already exists at $SSH_KEY"
fi

# 5. Swarm Configuration (SWARM_KEY)
if [ -z "$SWARM_KEY" ]; then
    if [ -f .env ]; then
        echo ">>> 📂 Loading SWARM_KEY from .env..."
        source .env
    fi
fi

if [ -z "$SWARM_KEY" ]; then
    echo ">>> ⚠️ SWARM_KEY (Ensemble Secret) not detected."
    read -p "Enter SWARM_KEY [KEYSTONE-POLYPHONY-UPSTREAM]: " input_key
    export SWARM_KEY=${input_key:-"KEYSTONE-POLYPHONY-UPSTREAM"}
    echo "✅ SWARM_KEY set to $SWARM_KEY"
fi

# 6. Swarm Initialization & Key Exchange
echo ">>> 🐝 Starting Swarm & Exchanging SSH Keys..."
# This script uses LiminalMesh which starts the Node sidecar internally.
python3 scripts/exchange_ssh_keys.py --duration 30

echo ">>> 🎉 Ensemble Setup Complete!"
echo ">>> You can now multiply this environment, and nodes will automatically discover each other via the swarm."
