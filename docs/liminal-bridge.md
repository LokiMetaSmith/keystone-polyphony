# Liminal Bridge

Liminal Bridge is the coordination substrate used by Keystone Polyphony for multi-agent collaboration.
It provides shared context, lightweight locking, and optional planning assistance over a peer-to-peer mesh.

## Purpose and Scope

Liminal Bridge implements four collaboration primitives:

- Shared context: agents publish short state updates as `thoughts`.
- Mutex-style locking: agents acquire and release `batons` on resources such as file paths.
- Shared key/value state: agents write swarm-level values into `kv_store`.
- Planning loop: `Pulse` can consult `Architect` and publish a `master_plan` into the shared store.

Current implementation is intentionally lightweight and best-effort. It favors speed and ease of bootstrapping over strict distributed consistency.

## Architecture

```mermaid
graph TD
    Client["MCP Client"] --> MCP["FastMCP Server"]
    MCP --> Mesh["LiminalMesh Python"]
    Mesh --> Sidecar["Node Sidecar"]
    Sidecar --> Swarm["Hyperswarm Topic"]
    Swarm --> PeerA["Peer Node A"]
    Swarm --> PeerB["Peer Node B"]
    Mesh --> Pulse["Pulse Coordinator"]
    Pulse --> Architect["Architect LLM"]
    Architect --> Pulse
    Pulse --> Mesh
```

### Component Responsibilities

- `src/liminal_bridge/server.py`: exposes MCP tools and manages run modes (`mcp` and `seed`).
- `src/liminal_bridge/mesh.py`: in-memory shared state, message handling, lock behavior.
- `src/liminal_bridge/sidecar/bridge.js`: peer discovery and peer message transport through Hyperswarm.
- `src/liminal_bridge/pulse.py`: controlled trigger path for planner consultation.
- `src/liminal_bridge/architect.py`: optional LLM-backed planner (`DUCKY_API_KEY`, `DUCKY_MODEL`).

## Shared State Model (Liminal Space)

`LiminalMesh` maintains three in-memory maps:

| Store | Shape | Meaning |
|---|---|---|
| `thoughts` | `origin_node_id -> content` | Most recent thought per agent |
| `batons` | `resource -> owner_node_id` | Current lock owner per resource |
| `kv_store` | `key -> value` | Shared application values (for example `master_plan`) |

Important: these stores are process-local and ephemeral. They are not persisted across restarts.

## Wire Protocol

Messages are line-delimited JSON. Every outbound broadcast from Python adds:

- `origin`: sender node id.
- `timestamp`: sender wall-clock timestamp.

Application payload message types:

| Type | Producer | Consumer behavior |
|---|---|---|
| `thought` | any node | writes `thoughts[origin] = content` |
| `kv_update` | any node | writes `kv_store[key] = value` |
| `baton_request` | lock requester | if local node owns the resource, sends `baton_deny` |
| `baton_deny` | current owner | requester resolves acquisition attempt as denied |
| `baton_claim` | requester after timeout | receivers set `batons[resource] = origin` |
| `baton_release` | current owner | receivers remove baton if owner matches origin |

## Operational Flows

### 1) Swarm Registration and Tool Use

```mermaid
sequenceDiagram
    participant C as MCP Client
    participant S as server.py
    participant M as LiminalMesh
    participant J as bridge.js
    participant N as Peer Nodes

    C->>S: register_to_swarm(optional github_secret)
    S->>M: start()
    M->>J: spawn node sidecar with topic hash
    J->>N: join Hyperswarm topic
    S-->>C: connected node id and topic prefix

    C->>S: share_thought or acquire_baton or peek_liminal
    S->>M: execute action
    M->>J: broadcast payload as JSON line
    J->>N: relay to connected peers
```

### 2) Baton Acquire Flow

```mermaid
sequenceDiagram
    participant A as Requester
    participant B as Current Owner
    participant P as Other Peers

    A->>P: baton_request(resource)
    alt Owner exists and is B
        B->>A: baton_deny(resource,target)
        A-->>A: acquisition returns false
    else No deny before timeout
        A-->>A: timeout expires
        A->>P: baton_claim(resource)
        A-->>A: acquisition returns true
    end
```

### 3) Baton Release and Optional Planning Trigger

```mermaid
sequenceDiagram
    participant O as Owner
    participant P as Peers
    participant U as Pulse
    participant R as Architect

    O->>P: baton_release(resource)
    alt resource contains main or core or api
        O->>U: on_baton_release(resource)
        U->>R: consult(swarm_state)
        R-->>U: backlog json
        U->>P: kv_update(master_plan)
    else Non-critical resource
        O-->>O: no pulse trigger
    end
```

### 4) Seed Mode Background Pulse

```mermaid
flowchart TD
    Start["Start seed mode"] --> Join["Start mesh and join topic"]
    Join --> Loop["Sleep 1 second loop"]
    Loop --> CheckTimeout{"Timeout reached"}
    CheckTimeout -- Yes --> Stop["Stop mesh"]
    CheckTimeout -- No --> Tick{"Current second % 60 == 0"}
    Tick -- Yes --> Trigger["Pulse trigger seed_heartbeat"]
    Tick -- No --> Loop
    Trigger --> Loop
```

## Running Liminal Bridge

### Prerequisites

- Python environment with project dependencies installed.
- Node.js installed.
- Sidecar dependencies installed:

```bash
npm install --prefix src/liminal_bridge/sidecar
```

### Start MCP Mode (default)

```bash
export SWARM_KEY="replace-with-shared-secret"
python src/liminal_bridge/server.py --mode mcp
```

### Start Seed Mode

```bash
export SWARM_KEY="replace-with-shared-secret"
python src/liminal_bridge/server.py --mode seed --timeout 600
```

Seed mode keeps one node online to aid peer discovery and periodically attempts pulse checks.

### Run the Local Smoke Simulation

```bash
python simulate_swarm.py
```

This launches two local agents with scripted thought/lock actions so you can observe baton arbitration and shared-thought propagation.

## MCP Tool Contract

| Tool | Inputs | Behavior | Return shape |
|---|---|---|---|
| `register_to_swarm` | `github_secret` optional | starts mesh; if secret differs, recreates mesh with new topic | status string with node id and topic prefix |
| `share_thought` | `thought` string | auto-starts mesh if needed, writes local thought, broadcasts thought | fixed string `Thought streamed.` |
| `acquire_baton` | `file_path` string | auto-starts mesh if needed, runs deny-or-timeout lock attempt | `SUCCESS: ...` or `DENIED: ...` string |
| `release_baton` | `file_path` string | auto-starts mesh if needed, releases only if this node owns baton; then evaluates pulse trigger heuristic | status string |
| `peek_liminal` | `key` optional | returns one key from `kv_store` or full liminal snapshot | Python stringified dict/value (not strict JSON) |
| `consult_architect` | `context` string | auto-starts mesh if needed, calls `Pulse.trigger("manual:<context>")`, reads `master_plan` from KV | status string containing plan |
| `ensemble_chat` | `topic` string, `message` string | auto-starts mesh if needed, posts a persistent message to a topic-based thread | confirmation string |
| `get_ensemble_chat` | `topic` string | auto-starts mesh if needed, retrieves the persistent history of a discussion topic | JSON array of messages |

`Pulse` has a 5-minute cooldown. Repeated `consult_architect` calls inside the cooldown window may return an unchanged plan. Current MCP tools do not pass the special `force` context.

## Guarantees and Non-Guarantees

What the current system guarantees:

- Nodes sharing the same `SWARM_KEY` topic can exchange JSON messages.
- Local callers get immediate lock decisions when resource state is already known.
- `master_plan` updates are broadcast through the same mesh path as other updates.

What it does not guarantee yet:

- Durable state across process restart.
- Strongly consistent lock ownership under partitions or simultaneous timeout claims.
- Authenticated per-agent identities.
- Deterministic conflict resolution beyond last-write-wins style overwrites.

## Known Limitations and Roadmap Alignment

The implementation intentionally leaves several distributed-system concerns open. Planned follow-ups are tracked in `TODO.md`, including:

- persistence and snapshotting,
- CRDT and vector-clock improvements,
- per-agent identity and key rotation,
- stronger observability and load testing.

## Troubleshooting

- No peers discovered: verify all nodes use the same `SWARM_KEY` and can run Node sidecar.
- `Architect not configured`: set `DUCKY_API_KEY` and ensure `openai` package is installed.
- Baton behavior appears inconsistent: this can happen during concurrent timeout-based claims; treat current locking as cooperative best-effort.
