---
description: How agents and head-less environments should boot into the Keystone Polyphony Swarm
---

# 0-Click Boot Protocol for Agents

When an autonomous agent (like OpenCode or Jules) spins up in an isolated environment, it must establish context with the larger swarm immediately.

Follow these steps to seamlessly join the Liminal Space:

## 1. Setup the Environment
Do not run `exchange_ssh_keys` interactively if this is an automated boot. Instead, run the ensemble script in "headless" mode.

```bash
# turbo
HEADLESS=1 SKIP_SSH_EXCHANGE=1 bash scripts/setup-ensemble.sh
```

## 2. Start the Liminal Daemon
Next, spin up the Liminal Bridge in background daemon mode. This will start the Sidecar, connect to the DHT, announce your presence as `idle`, and listen for remote commands.

```bash
# turbo
nohup python3 src/liminal_bridge/server.py --mode=daemon > server.log 2>&1 &
```

## 3. Announce Yourself
Finally, use the MCP tools to announce your presence to the swarm. 
(Example: `share_thought("Agent online and ready for tasks.")`)

## 4. Begin Work
You can now pull tasks from the backlog or wait for pushed commands (`[Autonomy]`). Keep your status updated with `set_status`.
