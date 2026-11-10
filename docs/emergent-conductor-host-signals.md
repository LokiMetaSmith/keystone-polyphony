# Emergent Conductor Leases & Gated Host Signal Outbox (Slice 5)

This document specifies the architecture and operation of **Slice 5** of the Keystone Polyphony collaboration protocol:
1. **Emergent Conductor Leases**: Dynamically electing an idle worker as a non-coding Conductor to steer swarms, decompose contested tasks, and emit scaling telemetry.
2. **Gated Host Signal Outbox**: A secure, decoupled dual-key channel enabling internal swarm agents to signal external execution environments (e.g. OpenJules) to scale container cohorts or break review deadlocks.

---

## 1. Dual-Key Perimeter Architecture

To maintain strict isolation between untrusted task execution within the swarm and privileged container infrastructure:

```
┌────────────────────────────────────────┐         ┌───────────────────────────────────────┐
│       Swarm Agents (Inside Swarm)      │         │     External Host Orchestrator        │
│       Authenticated via SWARM_KEY      │         │    Authenticated via OPENJULES_HOST_KEY│
└──────────────────┬─────────────────────┘         └──────────────────┬────────────────────┘
                   │                                                  │
                   │ Emit Host Signals                                │ Poll / Fulfill
                   ▼                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             Fenced SQLite Ledger (WAL Mode)                              │
│                                                                                          │
│  - conductor_state (Singleton Lease + Monotonic Fence Token)                             │
│  - host_signal_outbox (Signals, Cost Snapshots, Deduplication, Host Acks)                │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

* **`SWARM_KEY` Perimeter**: Agents inside the swarm interact with tasks, claim conductor leases, and emit advisory signals into the outbox. Swarm agents **cannot** fulfill or acknowledge host signals.
* **`OPENJULES_HOST_KEY` Perimeter**: External host runners poll pending signals, provision or tear down container runners, and acknowledge signals with status updates (`ACKNOWLEDGED`, `FULFILLED`, `REJECTED`).

---

## 2. Emergent Conductor Role

The Conductor is a **strictly non-coding, advisory agent role**.

### Invariants:
1. **Coding Lease Exclusion**: Any agent holding an active coding assignment (`assigned` or `running` with `lease_expires_at > now`) is strictly barred from claiming the Conductor lease (`409 Conflict`).
2. **Chamber Mode**: In small swarms with fewer than 3 active workers and no tasks awaiting integration review (`integrating` or `held`), Conductor lease acquisition is rejected unless `force_for_solo_deadlock=True`.
3. **Monotonic Fencing**: The singleton Conductor lease tracks an incrementing `fence_token`. When a lease expires (default TTL: 90s), any idle agent can claim the podium with `fence_token + 1`.
4. **Step-Down**: An agent holding the Conductor role can call `step_down_conductor` to release the lease, immediately freeing itself to acquire a coding or review assignment.

---

## 3. Host Signal Outbox

### Signal Types:
* `SCALE_UP`: Request addition of worker containers (e.g., expanding from 6 to 18 workers during backlog surges). *Conductor only.*
* `IDLE_DRAIN`: Request scale-down or termination of idle containers. *Conductor only.*
* `ESCALATE_TRIAGE`: Request human operator review when tasks encounter recurring failures. *Conductor only.*
* `SPAWN_REVIEWER`: Request an independent reviewer container. *Authorized for the Conductor OR a solo worker whose candidate is stuck in `INTEGRATING`.*

### Invariants:
* **Deduplication**: Repeated emission requests with identical `signal_type` and sorted `target_task_ids` return the existing `PENDING` signal without creating duplicate rows.
* **Holistic Cost Snapshot**: Every emitted signal captures `unsettled_cost_snapshot`, defined globally across all tasks in the ledger:
  $$\text{unsettled\_cost\_snapshot} = \sum_{\text{all tasks}} (\text{settled\_budget} + \text{in\_flight\_reserved\_budget})$$

---

## 4. MCP Tools Reference

| MCP Tool | Authentication | Description |
|---|---|---|
| `claim_emergent_conductor(actor_id, swarm_key, lease_ttl)` | `SWARM_KEY` | Claim singleton Conductor podium |
| `step_down_conductor(actor_id, fence_token, swarm_key)` | `SWARM_KEY` | Release Conductor role to resume coding |
| `request_host_scaling(actor_id, signal_type, requested_worker_delta, target_task_ids, rationale, swarm_key)` | `SWARM_KEY` | Emit scaling signal into host outbox |
| `openjules_poll_outbox(host_key, status_filter)` | `OPENJULES_HOST_KEY` | Poll outbox signals |
| `openjules_ack_signal(signal_id, new_status, response_note, host_key)` | `OPENJULES_HOST_KEY` | Acknowledge/fulfill signal |

---

## 5. CLI Usage

The commands are also available via the `polyphony conductor` CLI:

```bash
# Conductor Lease Management
polyphony conductor claim --actor-id agent_1 --ttl 90
polyphony conductor status
polyphony conductor step-down --actor-id agent_1 --fence 1

# Host Signal Outbox
polyphony conductor emit-signal --actor-id agent_1 --signal-type SCALE_UP --delta 3 --targets task_1,task_2 --rationale "Backlog spike"
polyphony conductor poll-signals --status PENDING
polyphony conductor ack-signal --signal-id sig_1234 --new-status FULFILLED --note "Spawned 3 runners"
polyphony conductor prune-signals --older-than 86400
```
