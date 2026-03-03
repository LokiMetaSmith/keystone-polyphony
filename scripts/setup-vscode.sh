#!/usr/bin/env bash

set -e

# Base directory for VSCode globalStorage
if [[ "$OSTYPE" == "darwin"* ]]; then
    VSCODE_USER_DIR="$HOME/Library/Application Support/Code/User/globalStorage"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    VSCODE_USER_DIR="$HOME/.config/Code/User/globalStorage"
else
    echo "Unsupported OS for automated VSCode setup. Please configure manually."
    exit 1
fi

CLINE_DIR="$VSCODE_USER_DIR/saoudrizwan.claude-dev/settings"
ROO_CODE_DIR="$VSCODE_USER_DIR/rooveterinaryinc.roo-cline/settings"
CONTINUE_DIR="$HOME/.continue"

# Get absolute paths
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_SCRIPT="$REPO_DIR/src/liminal_bridge/server.py"

# Use current python executable
PYTHON_EXEC=$(command -v python3 || command -v python)

if [ -z "$PYTHON_EXEC" ]; then
    echo "Error: Python executable not found."
    exit 1
fi

echo "Injecting Keystone Polyphony MCP server into VSCode extensions..."

# Python script to handle Cline and Roo Code
cat <<EOF | "$PYTHON_EXEC"
import json
import os
import sys

cline_dir = os.path.expanduser("$CLINE_DIR")
roo_code_dir = os.path.expanduser("$ROO_CODE_DIR")
repo_dir = "$REPO_DIR"
server_script = "$SERVER_SCRIPT"
python_exec = "$PYTHON_EXEC"
swarm_key = os.environ.get("SWARM_KEY", "liminal-default-secret")

def update_cline_mcp(target_dir, extension_name):
    settings_path = os.path.join(target_dir, "cline_mcp_settings.json")
    if not os.path.exists(target_dir):
        # We only want to inject if the extension is actually installed
        return

    try:
        with open(settings_path, 'r') as f:
            content = f.read().strip()
            settings = json.loads(content) if content else {}
    except FileNotFoundError:
        # Create it if the directory exists but the file doesn't
        settings = {}
    except Exception as e:
        print(f"Failed to read {settings_path} for {extension_name}: {e}")
        return

    if "mcpServers" not in settings:
        settings["mcpServers"] = {}

    settings["mcpServers"]["keystone-polyphony"] = {
        "command": python_exec,
        "args": [server_script, "--mode", "mcp"],
        "env": {
            "SWARM_KEY": swarm_key,
            "PYTHONPATH": repo_dir
        },
        "disabled": False,
        "autoApprove": []
    }

    try:
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=4)
        print(f"Successfully updated {extension_name} settings at {settings_path}")
    except Exception as e:
        print(f"Failed to write to {settings_path} for {extension_name}: {e}")

update_cline_mcp(cline_dir, "Cline")
update_cline_mcp(roo_code_dir, "Roo Code")
EOF

# Python script to handle Continue.dev
cat <<EOF | "$PYTHON_EXEC"
import json
import os
import sys

continue_dir = os.path.expanduser("$CONTINUE_DIR")
repo_dir = "$REPO_DIR"
server_script = "$SERVER_SCRIPT"
python_exec = "$PYTHON_EXEC"
swarm_key = os.environ.get("SWARM_KEY", "liminal-default-secret")

settings_path = os.path.join(continue_dir, "config.json")
if not os.path.exists(continue_dir):
    # Continue is not installed
    sys.exit(0)

try:
    with open(settings_path, 'r') as f:
        content = f.read().strip()
        settings = json.loads(content) if content else {}
except FileNotFoundError:
    settings = {}
except Exception as e:
    # Continue uses JSONC (JSON with comments) by default, which Python's json can't parse easily.
    # So we warn the user instead of destroying the file.
    print(f"Skipping Continue.dev setup: {settings_path} contains invalid JSON or comments: {e}")
    sys.exit(0)

if "experimental" not in settings:
    settings["experimental"] = {}

if "modelContextProtocolServers" not in settings["experimental"]:
    settings["experimental"]["modelContextProtocolServers"] = []

# Check if it already exists
mcp_servers = settings["experimental"]["modelContextProtocolServers"]
exists = False
for server in mcp_servers:
    if server.get("transport", {}).get("env", {}).get("PYTHONPATH") == repo_dir:
        exists = True
        break

if not exists:
    mcp_servers.append({
        "transport": {
            "type": "stdio",
            "command": python_exec,
            "args": [server_script, "--mode", "mcp"],
            "env": {
                "SWARM_KEY": swarm_key,
                "PYTHONPATH": repo_dir
            }
        }
    })

    try:
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=4)
        print(f"Successfully updated Continue.dev settings at {settings_path}")
    except Exception as e:
        print(f"Failed to write to {settings_path}: {e}")

EOF

echo ""
echo "Setup complete! If any extensions were detected, they have been updated."
echo "Restart VSCode for changes to take effect."