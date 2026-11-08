# Decision-gated admission to staging

Add the `decision-merge` label to a ready PR targeting `main` **before** its first
staging admission. This requests a full CLI review, validation, and a specialized
decision-model check. Accepted commits enter `staging`; the existing periodic
workflow still tests the staging snapshot before promoting it to `main`.

The gate does not directly merge into `main`. GitHub marks the PR merged when
its commits eventually reach the target branch through normal promotion.

## Sequence

1. `opencode.yml` or `workflow-review-dispatch.yml` reviews the full diff between
   captured base/head SHAs. Decision-enabled reviewers provide analysis and a
   GO/no-go recommendation, leaving approval to the gate.
2. The reviewer must itself explicitly pass, with zero blocking findings, and
   complete successfully. Its last nonempty output line must be a single,
   unfenced structured result, for example:

   ```text
   REVIEW_RESULT: {"verdict":"PASS","blocking_findings":0}
   ```

   A `FAIL`, missing/ambiguous/malformed verdict, conflicting duplicate markers,
   or nonzero blocking count fails the automatic review independently of any
   later decision. A passed reviewer publishes schema-v2 `review-evidence.json`, tied to the repository,
   PR, head/base SHAs, workflow path, run ID, and run attempt. A changed PR or
   failed/empty/oversized review does not produce usable evidence.
3. `decision-merge.yml` loads trusted default-branch code and validates the source
   workflow against the trusted base. PR content and artifact JSON are data;
   they are never executed by this privileged workflow.
4. The gate requires a ready, open, mergeable PR; fresh review evidence; no active
   changes-requested reviews or unresolved threads; and completed checks without
   failures. `pr-validation` must succeed by default. Successful reviewer/control
   jobs alone cannot satisfy test readiness. Checks on both the head and current
   synthetic merge commit are considered.
5. Only after the automatic review passes does the decision model classify the
   **complete independent review**, its reviewed file names, and verified CI and
   revision facts. The reviewer already examined the entire patch; this second
   stage interprets review findings for **staging admission**, rather than
   attempting another code audit from fragments of a patch. Five separate binary
   Decisions API questions estimate the probability that the review supports
   admission in correctness, security, test coverage, architecture, and compatibility.
   The repository computes the policy from these probabilities:

   - At least **four of five** areas must reach **80%** by default.
   - **Correctness and security must both pass**; other areas cannot offset them.
   - An **80% or higher** probability that the review contains an unresolved
     blocking finding vetoes admission independently of the five areas.

   The model classifies these questions; repository code decides whether this
   policy passes. It does not supply one global approval confidence. Refusal,
   malformed or missing probabilities, errors, and unmet policy hold admission.
   Model classifications are not measured probabilities of software correctness.
   The decision stage cannot override failed CI, an automatic review FAIL, stale
   revision evidence, unresolved threads, or change requests.
6. The gate rechecks current state, prepares a normal merge of the exact reviewed
   SHA, submits an approval tied to that commit, checks again, and pushes staging.
   It does not resolve conflicts with a preferred side or force-push. A conflicting
   merge or concurrent divergent staging update requires a retry or maintainer.

The two existing staging writers defer opted-in PRs to this gate and recheck the
live label before pushing. All staging writers share the same concurrency group.
Adding the label after a PR is already staged cannot retroactively gate it.

## Configuration

| Setting | Default / purpose |
| --- | --- |
| Repository secret `OPENROUTER_API_KEY` | Required for the decision request. |
| Repository variable `DECISION_MERGE_MODEL` | `auto`; ranked free Decisions API models with availability fallback. An explicit compatible model ID pins one model. |
| Repository variable `DECISION_MERGE_AREA_THRESHOLD` | `0.80`; threshold for each area, finite numeric value from `0.80` through `1.00`. Invalid values hold before any network request. The blocker veto remains fixed at `0.80`. |
| Repository variable `DECISION_MERGE_REQUIRED_CHECKS` | `pr-validation`; comma-separated successful check/status names. Other reported failures still block. |
| Repository secret `UPSTREAM_PR_TOKEN` | Optional staging push token, falling back to `GITHUB_TOKEN`. |
| Actions setting “Allow GitHub Actions to create and approve pull requests” | Required for the bot's native approval. Default workflow permissions can remain read-only. |

`pr-validation.yml` runs lint and the Python suite for opted-in ready PRs. It
checks out the PR candidate without persisted credentials and receives no model
or operational secrets. The privileged gate instead checks out the default branch.

The gate calls OpenRouter's typed
[Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request),
not chat completions. CLI review retains the separate free Nemotron model default.
The former `DECISION_MERGE_MIN_CONFIDENCE` variable is obsolete. Remove it before
using area policy; a nonempty old setting holds with a migration message rather
than silently treating global confidence as an area threshold.

Approval policy and code execute in this repository; a remote model never supplies
commands. GitHub branch rules and repository permissions remain in force.

## Running and inspecting

Completed review workflows trigger evaluation automatically. A fifteen-minute
catch-up schedule retries fresh reviews held while CI was pending. It considers
up to 20 opted-in PRs and the latest 30 successful runs from each supported
reviewer. Artifacts expire after seven days; rerun a reviewer if evidence is no
longer available. Already staged commits do not cause another model request.

For a controlled trial, manually run **Decision-Gated Staging Admission** with a
review run ID and optional expected PR number. Leave **dry_run** enabled, its
manual default. An empty run ID scans opted-in PRs. Dry-run evaluates the same
policy and model but submits no approval and pushes no branch. Automatic events
apply accepted decisions.

Each run records a validated `decision-result.json` artifact and job summary.
Raw provider responses and credentials are not logged. A native approval may
remain if a later staging push is rejected; retries reuse an existing bot gate
approval for that exact SHA. Main promotion still requires staging tests.

OpenCode receives the full review prompt and diff through stdin. This avoids
Linux's per-argument size limit for large PRs; passing a long patch as one CLI
argument caused the original review failure. Explicit positional/flag modes for
custom runners remain available, with their platform argument-size limits.

## Bootstrap and held cases

Normal runs execute the default-branch gate and trusted-base evidence helper.
A fresh review is required after the schema-v2 upgrade; older evidence without
an explicit reviewer PASS is rejected. A PR changing its reviewer workflow
cannot normally certify that change with its own run.

The repository owner explicitly authorized a one-time installation for PR #86.
The admin-owned `DECISION_GATE_BOOTSTRAP_SHA` variable must pin the exact audited
feature commit before an owner push. Both reviewer checkout and provenance
checks restrict this path to that SHA, PR #86, the integration branch, the same
repository, the owner actor, and the original `main` base SHA. It still requires
a full independent reviewer PASS, passing PR validation, and passage of the
area policy by the decision model. The waiting job holds no staging lock;
only admission acquires the shared staging lock. Remove the bootstrap pin after
admission. Other PRs and later revisions retain normal trusted-base checks.

After admission, run **Periodic Test and Merge to Main** against the reviewed
feature revision for initial installation. It builds test dependencies without
workflow credentials, runs mandatory lint and pytest in a network-isolated
container, and promotes only the unchanged tested staging snapshot. Old
`HOURLY_TEST_COMMAND`/`HOURLY_TEST_IMAGE` variables cannot replace these checks.
A normal merge preserves PR ancestry so GitHub marks the original PR merged
when its commits reach `main`; native self-approval is not required.

The gate requires a complete text diff (at most 1,000,000 UTF-8 bytes) and review
text of at most 60,000 UTF-8 bytes. It retains the full-diff SHA-256 hash, byte
count, per-file manifest and hashes in the result as an audit binding to the
verified head/base revisions. The decision request contains the full review
without truncation, verified readiness facts, CI names/results, review model,
scope, changed file names, and the staging purpose. Raw patch text and crypto
identifiers are omitted from the classification request. Binary, omitted,
oversized, stale, or insufficiently scoped evidence holds before classification.

The previous implementation asked for a global decision on each 20 KB patch
partition, repeating the full review and hashes each time. Its observed 42%
first-partition hold did not include a rationale, so its exact cause is unknown.
That fragmented input mixed a second code audit with review interpretation and
made the score hard to diagnose. Area classification replaces that integration;
it does not guarantee that a particular PR passes. The workflow summary and
JSON artifact expose each area's probability, threshold, pass status, critical
status, blocker-veto probability, and final repository policy verdict.

Missing or pending checks hold the PR until the next retry; unresolved findings
require a new review or explicit resolution.

The decision picker uses only typed Decisions API models with zero prices for every advertised pricing component, never general
chat or paid fallbacks. Catalog lookup and up
to three ranked attempts share the gate's timeout. Availability, rate-limit,
transport, and malformed-response failures can try the next model. A valid
policy hold or refusal ends selection and holds admission;
it never retries to obtain an approval. The final decision records the actual
selected model. An explicit `DECISION_MERGE_MODEL` bypasses catalog selection and
fallback. See [model selection](model-picker.md) for ranking and catalog-outage behavior.

## Durable worker candidate records

The opt-in [durable collaboration prototype](durable-collaboration.md) can
preserve a reviewed patch and its requirements-bound admission packet before a
PR exists. That packet records local candidate acceptance, not release authority.
Creating a PR from it still requires this gate's independent workflow evidence
and CI bound to the PR's actual head/base SHAs. No local receipt substitutes for
GitHub authorization or the existing staging checks.
