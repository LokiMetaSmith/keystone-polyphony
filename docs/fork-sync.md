# LokiMetaSmith integration

On 2026-11-08, the integration branch fast-forwarded from `8f23c9c` to
[`a837308`](https://github.com/LokiMetaSmith/keystone-polyphony/commit/a837308)
from [LokiMetaSmith/keystone-polyphony](https://github.com/LokiMetaSmith/keystone-polyphony).
All 17 intervening commits and their author metadata are preserved.

The fork contributes MQTT/BLE transport routing and configuration, a Register
CRDT with caller-supplied conflict resolution and a legacy LWWRegister alias,
Docker module-entry fixes, and a review workflow that checks out trusted base
code rather than an untrusted pull-request head. Historical `lww-register`
records remain readable. Custom resolver callbacks are not used by replication;
callers must preserve CRDT convergence properties if they supply one.

Integration fixes ensure BLE tries every discovered matching advertisement,
registration preserves the selected storage backend and command callback, and
the distributed KV cache example imports its SQLite provider. Python files
changed by the fork are normalized with Black. MCP is constrained below version
2 because this code uses the 1.x FastMCP API; the unconstrained setup selected
an incompatible major release during validation.

Inspection also found a credential-capturing root npm install hook introduced
earlier by `befedc3`, already present in both histories. A separate commit removes
that manifest. It was not executed during this integration. Prior execution or
exposure has not been established; investigation is recorded in
`.github/issues/investigate-credential-capturing-install-hook.md`.

Ensemble setup was run with a fresh isolated swarm key, npm lifecycle scripts
disabled, and SSH exchange skipped. Architecture planning was recorded in an
isolated mesh chat and independently reviewed. A second ensemble implemented and
reviewed the [optional decision-model adapter and local demo](decision-models.md).
The existing user-owned `pr_body.md` was left untouched.

## Validation and limits

The full Python suite, repository lint script, and three-node local demo are the
integration checks. The demo uses production signed/encrypted mesh envelopes
over loopback and explicitly scripted role/model fixtures. It does not establish
live DHT discovery, broker delivery, BLE hardware behavior, or model-provider
availability. A subsequent
[live decision smoke test](https://github.com/niklas-olsson/keystone-polyphony/actions/runs/42519161170)
used the repository's OpenRouter secret through GitHub Actions and accepted a
real `continue` decision from `parallel/decisions-fast:free` with 0.873 confidence.
The Architect and role nodes remained scripted, with loopback transport.

The test suite has an existing asynchronous subprocess-cleanup warning, tracked
in `.github/issues/async-test-resource-cleanup.md`. MQTT/BLE delivery to mixed
transport peers and duplicate-command suppression need further work, tracked in
`.github/issues/mixed-transport-delivery.md`. Alternate transports and decision
models remain disabled unless configured.
