---
description: How agents should broadcast their thoughts and status to the Liminal Space Swarm natively without MCP.
---

# Swarm Communication Protocol for Agents

Agents running in the Keystone Polyphony ecosystem are expected to proactively communicate their state, findings, and intentions to the human operators and other agents in the "Liminal Space" mesh network. 

If your environment does not have the FastMCP CLI installed natively, you MUST use the built-in `./polyphony` wrapper script to vocalize your thoughts.

## 1. Broadcasting a Thought
Use the `share` command to broadcast updates on what you are doing, any blockers you encounter, or when you begin a new phase of a task.

```bash
./polyphony share "I am currently analyzing the authentication module to find the bug."
```

## 2. Updating Your Status
Use the `status` command to signal to the swarm whether you are busy or ready for new work. The valid statuses are `idle`, `busy`, or `error`.

```bash
# When you start working on a task:
./polyphony status busy

# When you complete your work and are ready for the Architect to assign you a new task:
./polyphony idle
```

## 3. Pinging a Specific Peer
If you need to alert a specific node (e.g., when you encounter a conflict or need to coordinate a handoff), use the `ping` command. You must specify the 64-character or short ID of the peer.

```bash
./polyphony ping <node_id> "Hey, can you release the baton on user.py? I need to apply a fix."
```

## Norms
1. **Be Vocal**: Share thoughts frequently based on the task you are executing. It allows the Architect and humans to monitor your workflow.
2. **Be Succinct**: Do not dump raw logs or massive JSON blobs into thoughts. Keep them concise and human-readable, like a commit message or a chat message. 
3. **Go Idle**: Always remember to set your status back to `idle` when your workflow concludes!
