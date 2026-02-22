# Feature: Make Issue Review Workflow Agent-Agnostic

Currently, the `jules-issue-reviewer.yml` workflow is specifically designed to assign issues to `@Jules` for review. However, this repository is intended to support collaboration between **multiple autonomous agents** (Jules, Codex, and others) as well as human reviewers.

## Goals
1. Decouple the review assignment workflow from any single agent identity.
2. Support a configurable list of reviewers (agents and/or humans) that can be assigned issues based on availability, specialization, or round-robin rotation.
3. Ensure all agent-specific workflows use a generic interface so that adding or removing an agent reviewer requires only a configuration change, not a code change.

## Proposed Approach (Starting Point)
- Introduce a repository variable (e.g., `ISSUE_REVIEWERS`) or a config file (e.g., `.github/reviewers.yml`) that lists eligible reviewers.
- The reviewer workflow reads this configuration and assigns based on defined strategy (round-robin, label-match, random, etc.).
- Rename `jules-issue-reviewer.yml` to something generic like `issue-reviewer.yml`.

## Acceptance Criteria
- [ ] The review workflow does not reference any hardcoded agent name.
- [ ] Adding a new agent reviewer requires only a config/variable change.
- [ ] Existing label lifecycle (`pre-review` → `jules`/`reviewed` → `ready for work`) generalizes to any reviewer identity.
- [ ] Documentation in `docs/ci-cd.md` is updated to reflect the agent-agnostic design.

## Prerequisites
- [ ] `jules-issue-reviewer.yml` must be merged and functional first (see: *Feature: Architect Pre-Commit and Pre-Push Hooks*).
