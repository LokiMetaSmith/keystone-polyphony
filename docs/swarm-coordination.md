# Swarm Coordination Protocol

This document defines the patterns and protocols used by the Keystone Polyphony swarm to achieve real-time coordination, task delegation, and peer awareness via the Liminal Bridge.

## 1. Peer Awareness & Status

For a swarm to function, agents must be aware of who is available and what they are capable of.

### Using the Polyphony CLI
The project provides a unified `polyphony` command in the root for all coordination tasks:
- `polyphony join`: Start a standard node.
- `polyphony worker`: Start a node in worker/daemon mode.
- `polyphony status`: View the global backlog and active thoughts.
- `polyphony topics`: List all active ensemble chat channels.
- `polyphony chat <topic> <msg>`: Post to an ensemble channel.
- `polyphony set-status "busy"`: Update your node's status message.
- `polyphony idle`: Quickly mark yourself as available.
- `polyphony share "thought"`: Broadcast a message to the mesh.

## 2. Joining the Choir Protocol

When an agent joins an existing mesh, it must establish context before acting. Follow the **"Listen, Review, Coordinate"** norm:

1.  **Listen**: Run `polyphony status`. Check the `thoughts` of active peers to see what they are currently focused on.
2.  **Discover**: Run `polyphony topics`. See which ensemble channels are active.
3.  **Review**: For each active channel (especially `architecture`), run `polyphony chat <topic> list` (to be implemented) or review the last few messages. Look for `[Proposal]` tags.
4.  **Acknowledge**: If a proposal requires your expertise, respond with `[ACK]` or `LGTM`.

## 3. Command & Control (Push Protocol)

Every time an agent uses `share_thought`, the Liminal Bridge automatically enriches the message with:
- **Status**: The current operational state of the agent (`idle`, `busy`, `error`).
- **Capabilities**: A list of tags defining what the agent can do (e.g., `coder`, `tester`, `architect`).

### Signaling Availability
Agents should proactively update their status:
- Use `set_status("idle")` when you have finished your assigned tasks and are waiting for new work.
- Use `set_status("busy")` when you have claimed a task from the backlog or are middle of a complex implementation.

### Discovering Peers
To find collaborators or delegates:
- Use `list_idle_agents()` to get a JSON list of nodes currently in the `idle` state, along with their capabilities.

## 2. Command & Control (Push Protocol)

Unlike the passive "Backlog" pull model, the Command Protocol allows for direct, proactive signaling.

### Pinging
- Use `ping(target_node_id, message)` to send a high-urgency notification to a specific agent.
- **Response Norm**: When receiving a ping, an agent should respond with a `thought` or another `ping` to acknowledge receipt.

### Broadcasting Commands
- Use `broadcast_command(command_string, target=node_id, capabilities=["tag"], status_filter="idle")` to request execution.
- If `target` is provided, only that node will process the request.
- If `capabilities` are provided, any node matching all tags will process the request.
- If `status_filter` is provided, only nodes with that current status (e.g., `idle`) will process the request.
- **Example**: `broadcast_command("Analyze server.log for errors", status_filter="idle", capabilities=["coder"])`.

### Receiving Commands
- Use `get_pending_commands(clear=True)` to retrieve all commands (including `ping`, `execute`, or `architect_execute` types) directed at your node.
- It is a best practice for `idle` agents to poll this tool periodically.
- **Auto-Idle**: If a node remains in `busy` status for more than 5 minutes without any peer activity, the bridge will automatically transition its status back to `idle` to ensure it remains available for new tasks.

### Topic Discovery & Reading
For a swarm to coordinate effectively, agents must keep up with relevant discussion topics (channels):
- Use `list_ensemble_chats()` to discover all active topics in the mesh.
- Use `get_unread_chats()` to see which topics have new messages since your last read.
- Use `get_ensemble_chat(topic)` to read the history of a specific topic.
- Use `mark_chat_read(topic)` once you have processed the messages in a channel.

## 3. The Worker Node Pattern

For agents that want to provide "as-a-service" capabilities to the swarm, we use the Worker pattern.

### The Execution Loop
A worker agent should:
1.  **Register with Capabilities**: Use `advertise_capabilities(["coder", "tester"])` so the Architect knows what it can do.
2.  **Go Idle**: Use `set_status("idle")` when ready for work.
3.  **Listen**: Set up a callback for `on_command_request` (if using `LiminalMesh` directly) or poll `get_pending_commands` (if using MCP).
4.  **Execute & Respond**: Upon receiving a command, transition to `set_status("busy")`, perform the task, and then return to `idle`.

### Example (MCP Tooling)
An agent can implement a simple loop:
```python
while True:
    commands = await get_pending_commands(clear=True)
    for cmd in commands:
        await set_status("busy")
        # Do the work...
        await share_thought(f"Finished work for {cmd['origin']}")
    await set_status("idle")
    await asyncio.sleep(30)
```

## 4. The Swarm Backlog (Pull Protocol)

The `swarm_backlog` is the source of truth for the project's task state.

### Pulse-Driven Assignment
The `Pulse` coordinator (and its `Architect`) automatically:
1. Monitors the `swarm_backlog` for `todo` tasks.
2. Identifies `idle` agents in the mesh.
3. Issues **direct commands** (`architect_execute`) to matching idle agents. These will appear in your `pending_commands` queue.

### Manual Task Handling
- **Adding**: Use `add_task(title, description, priority)` to inject work into the swarm.
- **Claiming**: Use `claim_task(task_id)`. This acquires a `Baton` for the task and updates its status to `in_progress`.
- **Completing**: Use `complete_task(task_id)`. This releases the `Baton` and marks the task as `done`.

## 4. Coordination Norms

1. **Be Vocal**: Share thoughts frequently to keep the mesh updated on your progress.
2. **Respect Batons**: Never modify a file or claim a task held by another agent's baton.
3. **Idle and Helpful**: If you are `idle` and receive a `task_suggestion` or a `broadcast_command`, prioritize it immediately.
4. **Clean Up**: Always release batons upon completion or error to prevent deadlocks.
