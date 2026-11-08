# Reliability: Account for OpenCode concurrent first-run database initialization

During the issue #95 live two-worker trial, two OpenCode 1.19.3 processes
started concurrently with the same fresh HOME. One exited with a SQLite
migration failure while creating the `workspace` table. The other worker
produced its expected file. This was observed with the free OpenRouter Nemotron
model; no provider failure was needed to trigger the local initialization race.

The durable trial uses an owner-approved separate HOME per attempt to avoid
coupling worker CLI state. Investigate whether normal ensemble launch paths
need a pre-initialization step or separate OpenCode data directories, and whether
the failure should be reported upstream to OpenCode. Reproduce with two
simultaneous first runs against a disposable HOME; preserve sanitized errors
and distinguish provider failure from CLI startup failure. Do not include API
keys, prompts containing private data, or raw session logs in the public issue.
