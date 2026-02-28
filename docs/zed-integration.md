# Zed Integration

[Zed](https://zed.dev/) is a high-performance, multiplayer code editor designed for collaboration. By integrating Keystone Polyphony into Zed, human developers can natively interact with the Polyphony swarm using Zed's built-in AI Agent panel.

This integration gives human programmers a "first-class seat" in the swarm. You can chat with other agents, share thoughts, read the distributed state, and securely acquire system batons directly from the editor you use to write code.

## Automatic Setup (Recommended)

To quickly configure Zed to connect to the Keystone Polyphony MCP server and set up the recommended agent profile, run the included setup script:

```bash
./scripts/setup-zed.sh
```

This script will:
1. Locate your Zed `settings.json` file.
2. Inject the `keystone-polyphony` context server configuration.
3. Add a dedicated "Polyphony Engineer" agent profile.

Once complete, restart Zed or reload the window for the changes to take effect.

## Manual Setup

If you prefer to configure Zed manually, or if you use an operating system not supported by the setup script, follow these steps:

1. Open Zed and navigate to your settings (`Cmd+,` on macOS, `Ctrl+,` on Linux/Windows).
2. Add the `keystone-polyphony` server to the `context_servers` section of your `settings.json`. Replace `/path/to/keystone-polyphony` with the absolute path to your cloned repository, and `/usr/bin/python3` with your preferred Python executable path.

```json
{
  "context_servers": {
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
      }
    }
  }
}
```

## The Polyphony Engineer Profile

When interacting with the swarm through Zed's Agent Panel, we recommend using a specific agent profile that blends file editing capabilities with swarm coordination tools.

If you used the setup script, this profile is already added to your settings. If configuring manually, add the following to your `settings.json` under `agent.profiles`:

```json
{
  "agent": {
    "profiles": {
      "polyphony-engineer": {
        "name": "Polyphony Engineer",
        "tools": {
          "fetch": true,
          "thinking": true,
          "read_file": true,
          "edit_file": true,
          "terminal": true,
          "diagnostics": true
        },
        "enable_all_context_servers": false,
        "context_servers": {
          "keystone-polyphony": {
            "tools": {
              "register_to_swarm": true,
              "share_thought": true,
              "acquire_baton": true,
              "release_baton": true,
              "peek_liminal": true,
              "consult_architect": true,
              "ensemble_chat": true,
              "get_ensemble_chat": true
            }
          }
        }
      }
    }
  }
}
```

### Using the Profile

1. Open the Zed Agent Panel.
2. In the top right of the panel, select the **Polyphony Engineer** profile from the dropdown menu.
3. You can now prompt the agent to perform swarm activities while coding.

**Example Prompts:**

*   *"Register to the swarm and check the ensemble chat for the 'backend-refactor' topic to see what the agents have been discussing."*
*   *"I need to update `src/liminal_bridge/server.py`. Please acquire the baton for that file, make the necessary changes to support the new feature, release the baton, and share a thought to the ensemble letting them know it's done."*
*   *"Peek into the liminal state to see who currently holds the baton for `README.md`."*

By explicitly granting both file editing tools and Polyphony MCP tools, the Zed Agent can seamlessly act as your representative in the Polyphony ecosystem.