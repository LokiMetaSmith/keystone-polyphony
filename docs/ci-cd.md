# Continuous Integration & Delivery (CI/CD)

This document outlines the automated pipelines that power the development lifecycle of this project. All automation is handled via GitHub Actions and can be found in the `[.github/workflows](../.github/workflows)` directory.

## Workflows Overview

### 1. Auto-merge PR to Staging
**Trigger:** `pull_request_target` (opened, synchronize, reopened, ready_for_review) against `main`.
**File:** `auto-merge-staging.yml`

This workflow enforces an "open-by-default" staging environment. Whenever a non-draft Pull Request is opened against the `main` branch, it is automatically merged into the `staging` branch so that it can be tested in an integrated environment.

```mermaid
graph TD
    A[PR to main opened or updated] --> B{Is PR a Draft?}
    B -- Yes --> End((Skip Workflow))
    B -- No --> C[Fetch or Create staging branch]
    C --> D[Fetch PR branch changes]
    D --> E[Merge PR branch into staging]
    E --> F[Push staging to remote]
```

### 2. Periodic Merge to Main
**Trigger:** `schedule` (every 20 minutes) or `workflow_dispatch`.
**File:** `hourly-merge-main.yml`

This scheduled job acts as the gatekeeper to production (`main`). It periodically checks the `staging` branch, runs all automated tests, and if everything passes cleanly, promotes staging into `main`. It also sweeps for any leftover issue files on `main` and publishes them.

```mermaid
graph TD
    A[Every 20 min or Manual Dispatch] --> B[detect-staging: Check for changes]
    A --> S[sweep-issues: Check for leftover issue files]
    B --> C{Are there new commits?}
    C -- No --> Skip((Skip Workflow))
    C -- Yes --> D[test-staging: Run tests in Docker container]
    D --> E{Do tests pass?}
    E -- No --> Fail((Pipeline Fails))
    E -- Yes --> F[merge-to-main: Verify & Merge staging to main]
    F --> G{Running on a Fork?}
    G -- No --> End((Done))
    G -- Yes --> H[create-upstream-pr: Open PR to upstream]
    H --> End
    S --> T{Issue files found?}
    T -- No --> Skip2((No-op))
    T -- Yes --> U[publish-swept-issues: Call agent-issues workflow]
```

### 3. Publish Agent Issues
**Trigger:** `push` modifying `.github/issues/*.md`, `workflow_call`, or `workflow_dispatch`.
**File:** `agent-issues.yml`

This workflow handles automated issue generation by AI agents. When markdown files are pushed to `.github/issues/`, this action parses them, translates them into actual GitHub Issues on the upstream repository, and applies the `pre-review` label to signal that the issue needs triage.

```mermaid
graph TD
    A[Agent pushes markdown to .github/issues/] --> B{Is GH_TOKEN set?}
    B -- No --> C((Skip Publish))
    B -- Yes --> D[Iterate markdown issue files]
    D --> E{Issue fingerprint exists upstream?}
    E -- Yes --> F[Skip creation]
    E -- No --> G[Ensure 'pre-review' label exists]
    G --> H[Create GitHub Issue with 'pre-review' label]
    F --> I[Remove markdown file from git]
    H --> I
    I --> J[Commit file removal & Push]
```

### 4. Issue Reviewer
**Trigger:** `issues` (labeled) or `workflow_dispatch`.
**File:** `issue-reviewer.yml`

When an issue is labeled with `pre-review`, this workflow assigns it to a reviewer (AI agent or human) defined in `.github/reviewers.yml`. It uses a round-robin strategy based on the issue number and checks per-reviewer rolling 24h quotas (defined as repository variables). Over-quota issues receive a `quota-hold` label and are retried automatically.

```mermaid
graph TD
    A[Issue labeled / workflow_dispatch sweep] --> B{Has 'pre-review' label?}
    B -- No --> Skip((Skip))
    B -- Yes --> C{Already has a reviewer?}
    C -- Yes --> Skip
    C -- No --> D[Assign Reviewer Round-Robin]
    D --> E{Under reviewer quota?}
    E -- No --> F[Apply 'quota-hold' label]
    E -- Yes --> G[Apply Reviewer label]
    G --> H[Post review instructions]
```

### 5. CLI Agent Issue Solver
**Trigger:** `issues` (labeled `ready for work`), `workflow_dispatch`.
**File:** `agent-issue-solver.yml`

This workflow autonomously implements solutions for issues marked as `ready for work`. It checks the `AGENT_DAILY_TASKS` quota, creates a feature branch, composes a prompt from the issue and repo context, and runs a pluggable CLI agent (e.g., OpenCode). If successful, it opens a Pull Request; otherwise, it labels the issue as `agent-failed`.

```mermaid
graph TD
    A[Issue labeled 'ready for work' / sweep] --> B{Under daily quota?}
    B -- No --> C[Apply 'quota-hold']
    B -- Yes --> D[Swap labels: 'ready for work' -> 'agent-working']
    D --> E[Checkout, create feat/agent-N branch]
    E --> F[Compose prompt & Run CLI agent]
    F --> G{Agent produced changes?}
    G -- No --> H[Label 'agent-failed', post comment]
    G -- Yes --> I[Push branch, open PR with 'agent-pr' label]
```

### 6. Label Contributors
**Trigger:** `pull_request` (closed).
**File:** `add-contributors.yml`

A community management workflow that ensures everyone who successfully merges code gets recognized. When a PR is merged, the author automatically receives the `CONTRIBUTOR` label (unless they are a bot).

```mermaid
graph TD
    A[Pull Request Closed] --> B{Is PR merged to upstream?}
    B -- No --> C((Skip))
    B -- Yes --> D{"Is Author a [bot]?"}
    D -- Yes --> C
    D -- No --> E{Does 'CONTRIBUTOR' label exist?}
    E -- No --> F[Create 'CONTRIBUTOR' label via API]
    F --> G[Apply label to the merged PR]
    E -- Yes --> G
```

---

## Issue Lifecycle

All agent-generated issues follow a label-driven state machine. Labels are created automatically by workflows if they do not already exist. Issue throughput is governed by repository variables (rolling 24h window), with variable names defined per-reviewer in `.github/reviewers.yml`, and the `AGENT_DAILY_TASKS` variable for implementing agents.

```mermaid
stateDiagram-v2
    [*] --> pre_review : Agent creates issue
    pre_review --> reviewer_assigned : Under quota — reviewer assigns
    pre_review --> quota_hold : Over quota — held for retry
    quota_hold --> reviewer_assigned : Periodic sweep retries
    reviewer_assigned --> reviewed : Reviewer completes review
    reviewed --> ready_for_work : Final approval
    ready_for_work --> agent_working : Under quota — agent assigned
    ready_for_work --> quota_hold : Over quota — held for retry
    quota_hold --> agent_working : Periodic sweep retries
    agent_working --> agent_failed : Agent failed
    agent_working --> agent_pr : Agent opened PR
    agent_pr --> [*] : PR merged

    pre_review : 🟡 pre-review
    quota_hold : ⏳ quota-hold
    reviewer_assigned : 🟣 [reviewer label]
    reviewed : 🟢 reviewed
    ready_for_work : 🔵 ready for work
    agent_working : 🔵 agent-working
    agent_failed : 🔴 agent-failed
    agent_pr : 🟣 agent-pr (Label on PR)
```
