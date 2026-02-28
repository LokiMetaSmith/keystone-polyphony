#!/usr/bin/env bash

set -e

# Path to Zed settings
if [[ "$OSTYPE" == "darwin"* ]]; then
    ZED_SETTINGS_PATH="$HOME/.config/zed/settings.json"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    ZED_SETTINGS_PATH="$HOME/.config/zed/settings.json"
else
    echo "Unsupported OS for automated Zed setup. Please configure manually."
    exit 1
fi

if [ ! -f "$ZED_SETTINGS_PATH" ]; then
    echo "Zed settings not found at $ZED_SETTINGS_PATH. Is Zed installed?"
    echo "Creating a default one..."
    mkdir -p "$(dirname "$ZED_SETTINGS_PATH")"
    echo "{}" > "$ZED_SETTINGS_PATH"
fi

# Get absolute paths
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_SCRIPT="$REPO_DIR/src/liminal_bridge/server.py"

# Use current python executable
PYTHON_EXEC=$(command -v python3 || command -v python)

if [ -z "$PYTHON_EXEC" ]; then
    echo "Error: Python executable not found."
    exit 1
fi

echo "Injecting Keystone Polyphony MCP server into Zed settings..."

# We use python to safely modify the JSON
cat <<EOF | "$PYTHON_EXEC"
import json
import os
import sys

settings_path = os.path.expanduser("$ZED_SETTINGS_PATH")
repo_dir = "$REPO_DIR"
server_script = "$SERVER_SCRIPT"
python_exec = "$PYTHON_EXEC"

try:
    with open(settings_path, 'r') as f:
        # Handle empty files
        content = f.read().strip()
        settings = json.loads(content) if content else {}
except Exception as e:
    print(f"Failed to read {settings_path}: {e}")
    sys.exit(1)

# Ensure context_servers exists
if "context_servers" not in settings:
    settings["context_servers"] = {}

# We default to injecting SWARM_KEY as 'liminal-default-secret'
# Users can change this in settings.json if needed.
# Alternatively, if they have one exported, we could use it:
swarm_key = os.environ.get("SWARM_KEY", "liminal-default-secret")

settings["context_servers"]["keystone-polyphony"] = {
    "command": python_exec,
    "args": [server_script, "--mode", "mcp"],
    "env": {
        "SWARM_KEY": swarm_key,
        "PYTHONPATH": repo_dir
    }
}

# Ensure agent exists
if "agent" not in settings:
    settings["agent"] = {}

# Ensure profiles exists
if "profiles" not in settings["agent"]:
    settings["agent"]["profiles"] = {}

# Add "Polyphony Engineer" profile
settings["agent"]["profiles"]["polyphony-engineer"] = {
    "name": "Polyphony Engineer",
    "tools": {
        "fetch": True,
        "thinking": True,
        "read_file": True,
        "edit_file": True,
        "terminal": True,
        "diagnostics": True
    },
    "enable_all_context_servers": False,
    "context_servers": {
        "keystone-polyphony": {
            "tools": {
                "register_to_swarm": True,
                "share_thought": True,
                "acquire_baton": True,
                "release_baton": True,
                "peek_liminal": True,
                "consult_architect": True,
                "ensemble_chat": True,
                "get_ensemble_chat": True
            }
        }
    }
}

try:
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=4)
    print("Successfully updated Zed settings.")
except Exception as e:
    print(f"Failed to write to {settings_path}: {e}")
    sys.exit(1)
EOF

echo ""
echo "Setup complete! Restart Zed or reload the window for changes to take effect."
echo "You can now select the 'Polyphony Engineer' profile in the Zed Agent Panel."
