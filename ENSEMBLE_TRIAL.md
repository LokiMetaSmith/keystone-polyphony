# Ensemble First Performance: The Swarm Backlog

To kickstart the choir, we need a shared understanding of the work ahead. We will implement a decentralized **Swarm Backlog** using the existing Liminal Bridge primitives.

## The Technical Challenge
Agents must collaborate to design and implement a shared `backlog` system where tasks can be added, claimed, and tracked without a central server.

### 1. The Discussion (Technical Consensus)
Before writing any code, all active agents MUST participate in a discussion on the `architecture` topic.
- Use `get_ensemble_chat("architecture")` to see existing proposals.
- Use `ensemble_chat("architecture", "[Proposal] {details}")` to contribute.
- **Goal**: Reach consensus on the JSON schema for a task object (e.g., `{"id": UUID, "title": string, "owner": node_id, "status": "todo"|"done"}`).

### 2. Implementation Strategy
Once the schema is agreed upon:
- Use a `GSet` or `ORSet` CRDT stored in the KV key `swarm_backlog`.
- Use `update_set("swarm_backlog", task_json)` to add tasks.
- Use `Batons` to claim a task (lock resource `task:{task_id}`).

### 3. The Performance
- Agent A: Posts the first task proposal.
- Agent B: Reviews and approves/suggests changes to the schema.
- Agent C (The Architect): Confirms the plan using `consult_architect`.
- All: Implement the first three tasks of the project through this collaborative loop.

"The bridge is built by those who sing together." 🐝🎻
