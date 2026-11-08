# Optional decision models

Pulse can ask a specialized decision model whether to consult the Architect or
continue the current plan. This is an optional coordination step; the Architect
still produces plans and commands, and CRDT replication never calls a model.

The default is disabled and follows the existing Architect path. To opt in, set
these environment variables before starting the bridge:

```bash
export LIMINAL_DECISIONS_ENABLED=true
export OPENROUTER_API_KEY='your-api-key'
export LIMINAL_DECISION_MODEL='parallel/decisions-fast:free'
export LIMINAL_DECISION_TIMEOUT=5
```

`LIMINAL_DECISION_MODEL` accepts another compatible Decisions API model ID, such
as a Jev model available through the provider. Consult the provider's current
model catalog for availability. These settings are separate from `DUCKY_MODEL`
and `DUCKY_API_KEY`, which continue to configure the Architect.

The adapter uses OpenRouter's
[Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)
at `POST https://openrouter.ai/api/alpha/decisions`, with `state` and a named
`choice` question. It does not use chat completions. The default model is
[Parallel Decisions Fast](https://openrouter.ai/parallel/decisions-fast:free).

Only a typed `consult_architect` or `continue` choice with finite confidence of
at least 0.8 is accepted. Missing credentials, refusals, invalid responses, low
confidence, HTTP errors, and timeouts all retain Architect consultation. The
timeout defaults to five seconds and is capped at thirty. The existing cooldown
also applies when the advisor chooses to continue. An explicit Pulse `force`
request bypasses both the advisor and the cooldown. A continue recommendation
cannot suppress creation of an initial master plan.

The model receives only the trigger category (routine, heartbeat, manual, baton
release, or other), thought and baton counts, whether a
master plan exists, and up to 100 task status/priority summaries, plus the total
task count. Shared thoughts, task descriptions, arbitrary KV data, credentials,
and node identities are omitted. Advice stays local in `Pulse.last_decision`;
the resulting Architect plan is replicated as before. Remote advice does not
change access checks, capability matching, baton acquisition, or task ownership.

## Repeatable local demo

After installing dependencies with `scripts/setup-ensemble.sh`, run:

```bash
.venv/bin/python scripts/demo-decision-ensemble.py
```

Three scripted role nodes (planner, implementer, reviewer) use isolated SQLite
stores and identities. An in-process loopback replaces sidecar I/O while retaining
the production encryption, signatures, receive checks, CRDTs, capability-based
task claim, and baton release. The script verifies all nodes agree on completion,
the master plan, and review chat.

The demo exercises production Pulse behavior with the actual disabled advisor
and explicit fixtures for continue/refusal. It makes no live model calls and
does not generate implementation code. HTTP adapter behavior is covered by
`tests/test_decisions.py`; Pulse integration by `tests/test_pulse_decisions.py`.
The implementation itself was developed with separate integration, adapter, and
demo agents and an architectural review.

To try a live decision, configure the variables above and trigger a routine
Pulse consultation through a running bridge. Inspect `pulse.last_decision` in
the host process to distinguish a provider decision from a fallback. A live
OpenRouter response, broker transport, and BLE hardware are separate from this
offline demonstration.
