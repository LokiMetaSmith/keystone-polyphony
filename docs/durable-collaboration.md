# Durable collaboration prototype

Issue [#95](https://github.com/niklas-olsson/keystone-polyphony/issues/95) adds an
opt-in single-host service alongside the existing mesh. Workers choose tasks;
the conductor advises; the coordinator checks protected operations. Existing
exploratory tasks keep their advisory mesh workflow.

The implementation uses Python's SQLite driver and existing aiohttp dependency.
Run all SQLite clients on one host, on a local filesystem. Remote workers use
the authenticated HTTP interface through an SSH tunnel. Never share the WAL
files over a network filesystem. The default listener is loopback only.

## Decisions and boundaries

Upgrading the CRDT batons cannot make destination writes atomic. A distributed
workflow platform would add deployment machinery beyond this prototype. The
selected design keeps a separate SQLite WAL authority and Git worktree adapter.
The [issue discussion](https://github.com/niklas-olsson/keystone-polyphony/issues/95#issuecomment-6728727526)
records alternatives and pass limits posted before implementation.

| Concern | Prototype rule |
| --- | --- |
| Worker choice | `select_task` executes in the worker. Capability, dependency, task-wide budgets, active executions and busy resources filter eligible work. |
| Fairness | Order by creation time with at most 120 seconds of priority advantage. New high-priority tasks cannot indefinitely displace older eligible work. |
| Intent | Durable attempt records announce intent; they do not authorize shared writes. Mesh `swarm_backlog`, `chat:*`, and thoughts remain advisory. |
| Protected destination | `write_resource` writes the coordinator's SQLite destination record. Lease ownership, deadline, fence, effect and retry receipt commit in one transaction. |
| External effects | Arbitrary merge, deployment, filesystem replacement, and provider requests are outside this destination contract. Add destination-side atomic fencing, idempotency and unknown-outcome reconciliation before enrolling such effects. |
| Exclusivity | Acquisition uses expected-fence CAS. Every new lease increments the fence. The acquisition CAS tuple also identifies retries and returns the original lease, even after expiry. A different duration with that tuple is rejected. |
| Retry identity | Attempt start keys and resource write keys are bound to authenticated worker plus payload. Lost responses return the committed result; changing the payload is rejected. |
| Permissions | Owner enrolls task requirements, checks, dependencies, reviewers, capabilities, and resource. Workers cannot change them. Only owner-authorized revisions change acceptance criteria. |
| Reviewer independence | Owner provisions credentials for distinct real principals. The HTTP service injects authenticated identity; two tokens for the same principal cannot review that principal's work. Owner must not register one person as two principals. |
| Cost | Unknown. Wall-time allocations and attempt counts are bounded; this is not a monetary billing limit. |

`Coordinator` is a trusted in-process authority API. Its methods must never be
exposed directly to untrusted callers. `coordinator_service` restricts operations
by role and binds identity before calling it. All workers execute as trusted
processes on the host: a worktree separates working files, **not host access**.
Do not treat bearer credentials or this adapter as a sandbox against malicious
processes that can read the owner's database, credentials, or other worktrees.

## Running the service and workers

Install `requirements.txt` and Git. The worktree adapter requires POSIX process
groups. From the repository root, generate local credentials and an approved
execution template:

```bash
mkdir -p .liminal
python3 - <<'PY'
import json, os, secrets, shutil
from pathlib import Path
root = Path('.liminal').resolve()
credentials = {}
for identity, role in [('owner', 'owner'), ('alice', 'worker'), ('bob', 'worker'),
                       ('reviewer', 'reviewer'), ('conductor', 'conductor')]:
    token = secrets.token_hex(32)
    credentials[token] = {'identity': identity, 'role': role}
    path = root / f'{identity}.token'
    path.write_text(token)
    path.chmod(0o600)
path = root / 'credentials.json'
path.write_text(json.dumps(credentials))
path.chmod(0o600)
config = {
    'repository': str(Path('.').resolve()),
    'root': str(root / 'worktrees'),
    'base': 'HEAD',  # owner-approved baseline, resolved to a commit at launch
    'command': [shutil.which('opencode'), 'run', '--pure', '-m',
                'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free'],
    'inherit_env': ['PATH', 'OPENROUTER_API_KEY'],
    'isolated_home': True,
}
(root / 'execution.json').write_text(json.dumps(config))
PY
```

Use an immutable commit for `base` when the baseline must stay fixed across
attempts. Set the API key in the service environment; it is not a database
record. Credentials, logs, execution configuration and worktrees live under the
ignored `.liminal/` directory. The service command is owner-selected argv, with
no shell expansion and no worker-selected executable or environment. By default
only PATH is inherited; explicitly approve additional environment entries.

```bash
python3 -m src.liminal_bridge.coordinator_service \
  --credentials .liminal/credentials.json --execution-config .liminal/execution.json
```

From another terminal, enroll a task through the owner's credential. The return
value has the new `task_v2_...` ID:

```bash
python3 - <<'PY'
import asyncio
from pathlib import Path
from src.liminal_bridge.coordinator_service import CoordinatorClient
async def main():
    client = CoordinatorClient('http://127.0.0.1:8766', Path('.liminal/owner.token').read_text())
    task = await client.call('enroll', title='Example',
        requirements='Implement the agreed example in the worktree. Do not commit.',
        checks=['tests', 'independent-review'], reviewers=['reviewer'])
    print(task['id'])
asyncio.run(main())
PY
POLYPHONY_WORKER_TOKEN="$(cat .liminal/alice.token)" \
  python3 -m src.liminal_bridge.worker --identity alice
```

With `isolated_home: true`, each attempt receives a private CLI HOME. This also
avoids OpenCode first-run migrations competing over a new shared session DB.
Use explicit approved configuration if the CLI needs additional settings.

Run a second worker using `bob.token` and `--identity bob`. Identity must match
the owner-provisioned principal. Tasks have three attempts and 900 seconds of
allocated command time by default. The worker default allocates 60 seconds per
attempt. Replacement workers consume the same task budget. Allocated time is
not refunded, including failed launches; increase budgets only through a future
explicit owner policy, never by silently restarting a task.

## Service interface

All routes require `Authorization: Bearer <token>`. Requests and records contain
approved public task data. Keep raw private material out of titles, requirements,
problem causes, work products, evidence and advice.

| Endpoint | Access and behavior |
| --- | --- |
| `GET /snapshot` | Authenticated readers; tasks, attempts, resources, candidates, work receipts, observations, advice, responses and durable event cursor. |
| `GET /events?after=N&timeout=30` | Wait for a committed sequence change, with at most 30 seconds before a recovery check. Service checks local storage every 100 ms; waiting makes no model calls. |
| `GET /artifacts/{sha256}` | Retrieve committed approved work, even after worker removal. |
| `POST /call/enroll`, `/revise` | Owner; fix or explicitly revise requirements and checks. Revision changes invalidate old admission. |
| `POST /call/start_attempt` | Worker supplies selected `task_id`, capabilities, seconds, retry key. Service validates limits; it never chooses a task. |
| `POST /execute` | Worker supplies its `attempt_id`. Service launches the owner-approved template once. Repeated calls observe the original launch. Unknown outcomes require reconciliation. |
| `POST /cancel` | Worker requests its own attempt stop. Only adapter confirmation releases its execution reservation. |
| `POST /call/acquire`, `/write_resource` | Worker; require live attempt permission and task resource authorization. |
| `POST /call/save_work`, `/candidate`, `/problem` | Worker; salvage and record progress. An expired attempt can still save work. It cannot write a protected destination. |
| `POST /call/evidence` | Reviewer; candidate ID, check, boolean result, exact input revision. Source identity and observation time are supplied by the service. Historical observations remain durable; the latest observation per reviewer/check applies. |
| `POST /call/accept`, `/admission` | Owner; acceptance requires all configured checks, authorized independent review, committed artifact, and current requirements revision. Returns a durable admission packet. |
| `POST /call/advise` | Conductor; fixed 60-second minimum interval per task, 300-second expiry. No enrollment, requirements edits, execution, or acceptance rights. |
| `POST /call/respond` | Worker records follow/decline/defer plus cause against unexpired, current advice. |
| `POST /call/observe` | Trusted owner recovery only; confirm a terminated execution after independently verifying it. Never infer death from elapsed time or a cancellation request. |

Call payloads correspond to method arguments in `coordinator.py`, excluding
`worker`, `reviewer` and `source`, which the service injects. A 409 is an unmet
precondition. Observe new state, select other work or wait; do not repeatedly
call a model on a busy resource. `Worker.tick()` makes one selection and
`Worker.run()` waits on events or a bounded outage recovery delay.
`advise_from_problems(client)` is the optional non-coding conductor entry point.

## Saved work, completion and repository admission

The store commits UTF-8 patch bytes (including Git binary patch text) in SQLite
before acknowledging their SHA-256 receipt. The 4 MB prototype limit is checked
before saving. Candidate identity hashes canonical JSON with explicit field
boundaries: task ID, base revision, patch digest, requirements text and revision.
An identical candidate cannot be relabeled with another author. Different base,
patch or requirements require new applicable evidence.

The trusted supervisor extracts a patch with `git add --all` and
`git diff --cached --binary --full-index <base>` after confirmed process exit.
This includes useful untracked work and work from timed-out attempts. Candidates
are preserved even if the command failed. A submitted candidate enters `awaiting_review`,
which prevents workers from spending more model calls on it while checks are
pending. Failed review makes the task eligible for another bounded attempt.
Only the current candidate can complete the task; earlier candidates and patches
remain available as salvage. Snapshots report remaining attempts/time and an
unresolved cause when a task budget is exhausted. Neither an exit code nor a worker's
completion claim proves acceptance. Review must check the proposed patch against
the stated baseline and requirements. Required check names can only be set by
the task owner; the owner must configure meaningful independent checks.

A new review observation withdraws an existing admission pending re-evaluation.
An owner revision withdraws admission too. Acceptance retries reuse the packet
until observations change. Accepted records remain durable, even if a later
revision supersedes them. The legacy MCP and dashboard completion methods
reject schema-v2 tasks and the reserved namespace before releasing batons or
changing completion state. The old autonomous mesh picker skips these tasks.
Raw CRDT messages cannot establish coordinator acceptance.

An admission packet contains exact candidate identity, author and attempt,
requirements revision, applicable reviewer observations, acceptance time and
`release_authorized: false`. Retrieve it with `/call/admission` and its patch
with `/artifacts/{patch}`. These are inputs for repository admission; they do
**not** authorize Git operations. For the existing
[decision-merge gate](decision-merge.md), create a PR from the reviewed patch and
run the existing SHA-bound workflow reviews and CI against its final head/base.
This prototype does not automatically import a packet as GitHub review evidence
or bypass that gate. The PR's resulting Git commit is a different identity from
the pre-PR patch candidate and must satisfy the gate's own checks.

## Failure, retention and private inputs

A coordinator/network outage holds protected writes and new acceptance. Work
already launched continues within its approved execution limits. Other local
independent actions do not require conductor permission. An unavailable service
cannot grant fresh shared permission. During graceful shutdown the service stops
serving requests and lets existing bounded adapter actions finish.

After supervisor loss, processes and cost are **unknown**. The adapter never
signals a remembered PID after restart (PID reuse can target unrelated work).
Deadline expiry revokes write permission, but does not prove process exit or
release task execution reservations. Inspect the host and use owner `observe`
only after verifying termination. Independently ready tasks remain selectable.
A live POSIX supervisor enforces the command deadline by killing its process
group and reaping its main child. This cooperative adapter does not contain
malicious processes that escape their group; use a sandbox/cgroup adapter before
claiming that stronger termination/isolation guarantee.

All task, attempt, work, review, admission and event records are retained
indefinitely in this prototype. No automatic garbage collection deletes useful
work. Worker worktrees and private adapter logs also remain until an owner
removes them; only committed SQLite artifacts are the recovery authority.
Worker deletion and service restart preserve these artifacts. Host-loss recovery
requires an owner-maintained SQLite online backup on storage surviving the host.
The prototype provides no automatic failover or backup schedule. Do not copy
only the main database while WAL transactions are active; use SQLite's backup
API or stop the service and preserve the complete database safely.

`ApprovedInputProvider.worker_input(task_id, public_requirements)` is an optional
trusted provider boundary. Its output goes directly to worker stdin, without
being stored as a public record. The default returns public requirements only.
A custom provider must return only owner-approved inputs. Raw private guidance,
directory structures and memories stay outside public task records. Logs are
local private files (0600), never automatically exported as artifacts. Review
work products before deliberately submitting them to this public collaboration
space. Worktrees are not a mechanism for hiding host files from a worker.

## Verification and pass limits

Limits were posted in the issue before development:

| Scenario | Required pass limit |
| --- | --- |
| Stale fence, duplicate protected effect, incorrect acceptance | Zero across deterministic adversarial tests. |
| Worker loss / authority reopen | 100% committed patch bytes and applicable evidence retained. |
| Two workers; conductor absent; one resource busy | Both independent tasks produce candidates; busy task allocates zero model calls. |
| Unknown termination / expired attempt | Same task remains reserved; old destination permission fails; independent tasks remain ready. |
| Failed or changed review/candidate/requirements | No acceptance or current admission until applicable evidence passes. |
| Lost response | Identical retries return saved receipt; changed payload rejected; one destination effect. |
| Repeated advice / exhausted budget | Fixed throttle/expiry and task-wide attempt/time caps. |
| Wakeup | Event recovery within 1 second in tests; at most 30-second idle recovery interval by default. |
| Legacy completion | Zero managed-task status changes or baton releases. |

Run deterministic verification:

```bash
PYTHONPATH=src:. .venv/bin/pytest -q tests/test_coordinator.py
```

Run the live two-worker trial with the key in the environment or `.env`:

```bash
.venv/bin/python scripts/trial-durable-collaboration.py --seconds 120
```

The trial uses a disposable repository, temporary HOME, explicit approved
provider environment and the repository's default free OpenRouter CLI model.
It starts two real OpenCode processes through the service and adapter, verifies
their file contents, independently records those checks under the reviewer
principal, accepts candidates, and reopens the store. No conductor runs. One
shared resource remains occupied. The JSON result reports elapsed time,
preserved candidates, blocked-task inference count, incorrect acceptances and
unknown cost. Provider/model availability may fail the live trial; such failure
must not be reported as a protocol pass. `--failure-logs` optionally saves
private diagnostic logs locally; never commit or publish them.
