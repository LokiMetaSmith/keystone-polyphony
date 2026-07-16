#!/bin/bash
# scripts/setup-ensemble.sh

set -e

echo ">>> 🚀 Initializing Polyphony Ensemble Baseline..."


# Detect python executable
if command -v python3 &>/dev/null && python3 -c "import sys" 2>/dev/null; then
    PYTHON_EXEC="python3"
elif command -v python &>/dev/null && python -c "import sys" 2>/dev/null; then
    PYTHON_EXEC="python"
else
    echo "❌ ERROR: Python is not installed or not working correctly."
    exit 1
fi

# Detect pip executable
if command -v pip3 &>/dev/null; then
    PIP_EXEC="pip3"
elif command -v pip &>/dev/null; then
    PIP_EXEC="pip"
else
    echo "❌ ERROR: Pip is not installed."
    exit 1
fi

# 1. Dependency Check
echo ">>> 🔍 Checking system dependencies..."

# Required commands - script will fail if missing
REQUIRED_CMDS=("node" "npm" "ssh-keygen")
for cmd in "${REQUIRED_CMDS[@]}"; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "❌ Error: $cmd is not installed."
        echo "💡 Hint: Please install $cmd using your package manager."
        exit 1
    fi
done
echo "✅ Required system dependencies found ($PYTHON_EXEC, $PIP_EXEC, node, npm, ssh-keygen)."

# Optional: Check for GitHub CLI (gh)
# Not required for basic mesh functionality; only needed for GitHub API interactions
if ! command -v "gh" &> /dev/null; then
    echo "⚠️  Warning: gh (GitHub CLI) is not installed."
    echo "   This is optional - needed for GitHub issue/PR automation but not required for mesh/swarm."
    echo "   To install: https://cli.github.com/manual/installation"
else
    echo "✅ GitHub CLI (gh) found."
fi

# 2. Python Dependencies
echo ">>> 🐍 Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    $PYTHON_EXEC -m venv .venv
    echo "✅ Virtual environment created at .venv"
fi

# Activate venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
fi

echo ">>> 📦 Installing Python dependencies inside venv..."
if [ -f "requirements.txt" ]; then
    $PIP_EXEC install -r requirements.txt
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

if [ -z "$SWARM_KEY" ]; then
    if [ -f .env ]; then
        echo ">>> 📂 Loading SWARM_KEY from .env..."
        set -a
        source .env
        set +a
    fi
fi

if [ -z "$SWARM_KEY" ]; then
    if [ "$HEADLESS" = "1" ] || [ "$CI" = "true" ] || [ ! -t 0 ]; then
        echo ">>> ⚠️ Non-interactive environment detected. Using default SWARM_KEY."
        export SWARM_KEY="KEYSTONE-POLYPHONY-UPSTREAM"
    else
        echo ">>> ⚠️ SWARM_KEY (Ensemble Secret) not detected."
        read -p "Enter SWARM_KEY [KEYSTONE-POLYPHONY-UPSTREAM]: " input_key
        export SWARM_KEY=${input_key:-"KEYSTONE-POLYPHONY-UPSTREAM"}
    fi
    echo "✅ SWARM_KEY set to $SWARM_KEY"
fi

# 5b. Create .env file if not exists
if [ ! -f .env ]; then
    echo ">>> 📝 Creating .env file with SWARM_KEY..."
    echo "SWARM_KEY=$SWARM_KEY" > .env
    echo "✅ Created .env file"
else
    echo "ℹ️ .env file already exists"
fi

# 6. Swarm Initialization & Key Exchange
if [ "$SKIP_SSH_EXCHANGE" = "1" ]; then
    echo ">>> 🐝 Skipping Swarm Key Exchange (SKIP_SSH_EXCHANGE=1)..."
else
    echo ">>> 🐝 Starting Swarm & Exchanging SSH Keys..."
    # This script uses LiminalMesh which starts the Node sidecar internally.
    $PYTHON_EXEC scripts/exchange_ssh_keys.py --duration 30
fi

echo ">>> 🎉 Ensemble Setup Complete!"
echo ">>> You can now multiply this environment, and nodes will automatically discover each other via the swarm."
