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
5. Only after the automatic review passes does the decision model receive the
   full bounded diff and substantive review. Large diffs are partitioned into
   ordered requests of at most 20,000 UTF-8 bytes, preferring file boundaries.
   Every request includes the full independent review, CI results, exact SHAs,
   full file manifest and hashes, full-diff hash, and chunk index/count. Every
   chunk must **separately** approve; one hold, refusal, or failure stops the
   sequence without staging any part of the PR. Only
   a typed `approve` choice with confidence at least **0.95** by default allows admission. Administrators
   may explicitly configure another threshold from **0.80** through **1.00**;
   this never permits a `hold` or refusal to approve.
   A refusal, hold, low confidence, malformed response, missing key, or error
   leaves the PR out of staging. The decision model cannot override a failed
   automatic review. Confidence is model output, not a proof of safety.
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
| Repository variable `DECISION_MERGE_MIN_CONFIDENCE` | `0.95`; administrator confidence threshold, finite numeric value from `0.80` through `1.00`. Invalid values hold before any network request. |
| Repository variable `DECISION_MERGE_REQUIRED_CHECKS` | `pr-validation`; comma-separated successful check/status names. Other reported failures still block. |
| Repository secret `UPSTREAM_PR_TOKEN` | Optional staging push token, falling back to `GITHUB_TOKEN`. |
| Actions setting “Allow GitHub Actions to create and approve pull requests” | Required for the bot's native approval. Default workflow permissions can remain read-only. |

`pr-validation.yml` runs lint and the Python suite for opted-in ready PRs. It
checks out the PR candidate without persisted credentials and receives no model
or operational secrets. The privileged gate instead checks out the default branch.

The gate calls OpenRouter's typed
[Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request),
not chat completions. CLI review retains the separate free Nemotron model default.
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
a full independent reviewer PASS, passing PR validation, and approval of every
diff partition by the decision model. The waiting job holds no staging lock;
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
text of at most 60,000 UTF-8 bytes. It partitions rather than truncates large
diffs, including oversized lines without splitting UTF-8 characters. Small PRs
need one decision request. Results record every evaluated chunk, its actual
model, and the minimum confidence across decisions. It holds binary, omitted,
larger, stale, or workflow-only evidence for application changes rather than silently truncating
the decision input. The provider can impose a smaller context budget, in which
case its error also holds admission. Missing or pending checks hold the PR until
the next retry; unresolved findings require a new review or explicit resolution.

The decision picker uses only typed Decisions API models with zero prices for every advertised pricing component, never general
chat or paid fallbacks. Catalog lookup and up
to three ranked attempts share the gate's timeout. Availability, rate-limit,
transport, and malformed-response failures can try the next model. A valid
`hold`, low-confidence decision, or refusal ends selection and holds admission;
it never retries to obtain an approval. The final decision records the actual
selected model. An explicit `DECISION_MERGE_MODEL` bypasses catalog selection and
fallback. See [model selection](model-picker.md) for ranking and catalog-outage behavior.
