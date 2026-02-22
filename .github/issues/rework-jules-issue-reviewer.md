# Rework Issue Pipeline — Agent-Powered Triage Before Publish

## Problem

The current flow has two disconnected steps:

1. **`agent-issues.yml`** publishes raw `.github/issues/*.md` files as GitHub issues immediately.
2. **`jules-issue-reviewer.yml`** tries to refine them after the fact by posting a review-instructions comment.

This doesn't work because:

- Jules ignores comments — it only reads the issue body on assignment.
- Publishing first and refining later means noisy, incomplete issues hit the tracker before they're ready.
- The reviewer is Jules-specific, not extensible.

## Goal

Merge the two steps into a single **triage-then-publish pipeline** where:

1. A raw `<issue>.md` is dropped into `.github/issues/`.
2. Before publishing, the pipeline dispatches the raw issue to one or more **agents** for triage and refinement.
3. The agents mangle it into a well-structured format (clear acceptance criteria, BDD spec, explicit prerequisites).
4. The refined issue is then published to the GitHub tracker — already surgical, ready for work.

## Design Principles

- **Agent-agnostic**: Agents are configured via repository variable (`TRIAGE_AGENTS`), not hardcoded.
- **Refine before publish**: No raw/unreviewed issues hit the tracker.
- **Issue body is the contract**: Agents read and rewrite the `.md` file contents directly.
- **Composable agents**: Multiple agents can refine sequentially (e.g., agent A structures, agent B adds BDD spec).

## Proposed Pipeline

```
.github/issues/raw-idea.md
        │
        ▼
┌───────────────────┐
│  Triage Dispatch   │  Read TRIAGE_AGENTS variable
│                   │  Pick available agent(s)
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Agent Refinement  │  Agent reads the raw .md
│                   │  Rewrites it with:
│                   │   - Structured format
│                   │   - Acceptance criteria
│                   │   - BDD feature file
│                   │   - Dependency links
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Publish to GitHub │  Existing publish logic
│                   │  Issue is already refined
│                   │  Apply label: ready for work
└───────────────────┘
```

### Step 1: Triage Dispatch

- Read `TRIAGE_AGENTS` repo variable (ordered list of agent handles).
- For each raw `.md` file, assign to the first available agent respecting quota.
- The agent is given the raw file content and a refinement prompt.

### Step 2: Agent Refinement

The agent receives the raw issue and must return a structured version that satisfies:

- **Human Interaction Story** — clear narrative of how a contributor interacts with the feature.
- **BDD Feature File** — complete Cucumber `.feature` included.
- **Self-Contained** — prerequisites listed and marked as blocking.
- **Surgical Scope** — one concern per issue, no sprawling epics.

The mechanism for invoking the agent is implementation-dependent (Jules via assignment to a staging issue, CLI agents via subprocess, etc.) and should be abstracted behind a dispatch interface.

### Step 3: Publish

Once refined, the existing `agent-issues.yml` publish logic runs on the polished content. The `pre-review` label is replaced by `ready for work` since triage already happened.

## Open Questions

- **Blocking vs. async**: Should the pipeline block until the agent finishes refinement, or use a staging-issue pattern where the agent works async and a subsequent cycle picks up the result?
- **Fallback**: If no agent is available (quota exhausted), should the raw issue be published anyway with a `needs-triage` label, or held until the next cycle?
- **Multi-agent chaining**: Is sequential refinement by multiple agents needed now, or is single-agent sufficient for v1?

## Acceptance Criteria

- [ ] Raw issues in `.github/issues/` are refined by an agent before being published.
- [ ] Agent selection is driven by `TRIAGE_AGENTS` variable — no hardcoded agent names.
- [ ] Published issues meet the structured format (interaction story, BDD, self-contained).
- [ ] Quota enforcement works per-agent.
- [ ] `jules-issue-reviewer.yml` is removed or fully superseded.
- [ ] Retry-queue in periodic merge workflow triggers the new triage pipeline for unprocessed files.
- [ ] Fallback behaviour is defined for quota-exhausted scenarios.

## Labels

`pre-review`
