# Feature: Agent PR Review Dispatch for Workflow File Protection

## Context

We recently added a workflow protection gate (`auto-merge-staging.yml` + `workflow-review.yml`) that prevents PRs touching `.github/workflows/` from being auto-merged to staging. These PRs receive a `workflow-review` label and a comment tagging configured reviewers.

**The gap**: This works well for human reviewers (they see the GitHub notification and can approve via the UI), but **agent reviewers like Jules have no mechanism to act on PR review requests**. Jules currently operates on issues only (`issue-reviewer.yml` assigns issue triage, `agent-issue-solver.yml` solves issues). There is no equivalent workflow that dispatches a PR review task to an agent.

## Desired Behavior

When a PR is labeled `workflow-review`, an agent reviewer should be dispatched to:

1. **Inspect the PR diff** — specifically the changes to `.github/workflows/` files
2. **Evaluate security** — check for secret exfiltration, unauthorized external requests, privilege escalation, or malicious code patterns
3. **Evaluate value** — confirm the workflow changes serve a legitimate project purpose
4. **Submit a PR review** — either `gh pr review --approve` if benign, or `gh pr review --request-changes` with explanation if concerns are found

## Proposed Approach

Create a new workflow `workflow-review-dispatch.yml` that:

- **Triggers on**: `pull_request` labeled with `workflow-review`, or `workflow_dispatch` for sweep/retry
- **Quota**: Respects the existing reviewer quota system from `.github/reviewers.yml`
- **Agent dispatch**: Composes a security-focused prompt containing the PR diff for `.github/workflows/` files, the review criteria checklist, and repo context (`AGENTS.md`)
- **Agent action**: The agent runs and submits an actual GitHub PR review (`approve` or `request-changes`)
- **Integration**: A successful approval triggers the existing `workflow-review.yml` which merges to staging

This follows the same pattern as `agent-issue-solver.yml` but adapted for PR review instead of issue solving.

## Acceptance Criteria

- [ ] Agent reviewer can be dispatched automatically when a PR is labeled `workflow-review`
- [ ] Agent inspects only the workflow file diff, not the entire PR
- [ ] Agent submits a real GitHub PR review (approve/request-changes)
- [ ] Approved PRs flow through existing `workflow-review.yml` → staging merge
- [ ] Quota limits from `reviewers.yml` are respected
- [ ] Human reviewers can still approve independently (agent review is additive, not exclusive)

## References

- `auto-merge-staging.yml` — gates workflow-touching PRs
- `workflow-review.yml` — merges to staging on collaborator approval
- `agent-issue-solver.yml` — existing pattern for agent task dispatch
- `issue-reviewer.yml` — existing pattern for reviewer assignment with quotas
- `.github/reviewers.yml` — reviewer configuration
