# Mixed-transport swarm delivery

## Collaboration contract

The Liminal Mesh provides **best-effort peer notifications**, not durable
authority for protected task execution. For governed work, use the authenticated
durable coordinator, its revision-bound attempts and artifact receipts.
This separation preserves independent worker choice and conductor advice.

An outgoing broadcast receives a random 128-bit message ID. The payload is
encrypted and signed once. When MQTT or BLE is available, the same envelope is
sent through the optional transport and the Hyperswarm DHT sidecar. BLE attempts
each discovered matching peer even after individual failures.

A recipient checks the signature and origin before handling the payload.
For actionable `command_request` messages, it stores a bounded
deduplication receipt under the verified origin and message ID before invoking
a callback. Retries, duplicate links, and local process restart therefore
do not normally invoke the callback again within the retention window.

Target, capabilities, and status filters are **conjunctive**. A command
targeted at one node is not processed by another merely because it advertises
matching capabilities.

Macro and micro methods return an inspectable per-transport submission result.
`mqtt` and `dht` report `submitted`, `failed`, or `disabled`.
BLE also reports attempts and successful submissions to distinguish partial
peer coverage. A submission is **not** a recipient acknowledgement. If all
attempted transports fail, the original failure still raises.

## Explicit limitations

- A successful broker publish, BLE write, or DHT sidecar send does not prove
  receipt or execution by any remote node. Offline recipients can miss events.
- The receipt prevents duplicate local callback dispatch during its retention
  window. It is **not** an atomic receipt for the callback's external effects.
- Deduplication receipts are stored through the node's configured storage
  provider. Retention is bounded to at most 4096 receipts and a 24-hour age.
  Expired or evicted message IDs can be dispatched again.
- Legacy command messages without a message ID retain compatibility but do
  not receive replay protection. Upgrade producers before relying on the new
  behavior.
- The mesh callback and receipts do not authorize shared writes, task
  acceptance, PR admission, or deployment. Protected operations need the
  durable service's authenticated fencing, idempotency, budget and review
  checks.
- Full end-to-end command acknowledgement, child-specific supervision, and
  offline redelivery require separate work (draft #111). This change is the
  transport coverage and replay baseline for issue #90.

## Verification

The transport and command tests cover MQTT-only and DHT fallback, BLE partial
failure, same-message duplication across transports, persistence over process
restart, forged/incorrect targets, capability filters, malformed identifiers,
and available-route fallback. Hardware BLE and external MQTT infrastructure
are not exercised by the deterministic unit suite. The real DHT seed check is
a separate task (PR #105).
