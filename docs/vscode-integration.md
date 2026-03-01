# VSCode Integration

Visual Studio Code (VSCode) does not have a native "Agent" built-in by default, but it supports powerful AI extensions that connect to the Model Context Protocol (MCP). By installing these extensions, you can give yourself and your AI pair programmer a "first-class seat" in the Polyphony swarm.

We support integrating Keystone Polyphony with two popular AI extensions:
1.  **Cline** (and its popular fork, **Roo Code**)
2.  **Continue.dev**

## Automatic Setup (Recommended)

To quickly configure any of the supported VSCode extensions to connect to the Keystone Polyphony MCP server, run the included setup script:

```bash
./scripts/setup-vscode.sh
```

This script will attempt to locate the configuration files for Cline, Roo Code, and Continue, and inject the `keystone-polyphony` context server configuration for you.

## Manual Setup: Cline / Roo Code

[Cline](https://github.com/cline/cline) (formerly Claude Dev) and [Roo Code](https://github.com/RooVetGit/Roo-Code) are autonomous coding agents that live in your sidebar.

To add Keystone Polyphony manually:

1.  Open the MCP Servers configuration file.
    *   **macOS:** `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` (or `rooveterinaryinc.roo-cline` for Roo Code)
    *   **Windows:** `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`
    *   **Linux:** `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
2.  Add the `keystone-polyphony` entry under `mcpServers`. Replace the paths with the absolute path to your cloned repository and Python executable:

```json
{
  "mcpServers": {
    "keystone-polyphony": {
      "command": "/usr/bin/python3",
      "args": [
        "/path/to/keystone-polyphony/src/liminal_bridge/server.py",
        "--mode",
        "mcp"
      ],
      "env": {
        "SWARM_KEY": "liminal-default-secret",
        "PYTHONPATH": "/path/to/keystone-polyphony"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

## Manual Setup: Continue.dev

[Continue](https://continue.dev/) is a highly customizable AI assistant.

To add Keystone Polyphony manually:

1.  Open your Continue configuration file located at `~/.continue/config.json` (or click the gear icon in the Continue sidebar).
2.  Find the `experimental` block and add the `mcpServers` array inside it. Replace the paths with the absolute path to your cloned repository and Python executable:

```json
{
  "models": [ ... ],
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "/usr/bin/python3",
          "args": [
            "/path/to/keystone-polyphony/src/liminal_bridge/server.py",
            "--mode",
            "mcp"
          ],
          "env": {
            "SWARM_KEY": "liminal-default-secret",
            "PYTHONPATH": "/path/to/keystone-polyphony"
          }
        }
      }
    ]
  }
}
```

## Using the Swarm in VSCode

Once configured, your AI assistant in VSCode will automatically have access to the Polyphony tools.

**Example Prompts:**

*   *"Hey Cline, check the ensemble chat for the 'backend-refactor' topic to see what the swarm has been discussing."*
*   *"I need to update `src/liminal_bridge/server.py`. Please acquire the baton for that file using the Polyphony MCP tool, make the necessary changes to support the new feature, release the baton, and share a thought to the ensemble letting them know it's done."*
*   *"Peek into the liminal state to see who currently holds the baton for `README.md`."*
