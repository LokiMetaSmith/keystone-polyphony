# Contributing to Keystone Polyphony

This guide is the fastest path to making useful contributions.

## Quick Start

1. Fork the repository.
2. Create a branch from `main`.
3. If you run autonomous agents, complete the token setup in `Agentic Default Flow` before launching them.
4. Make your changes and run relevant checks locally.
5. Open a pull request to `niklas-olsson/keystone-polyphony:main` or let the agentic workflow open it.

Manual PRs are always supported and require no token setup.

## Agentic Default Flow (Required For Autonomous Runs)

If you want autonomous agents to submit upstream PRs without manual intervention, do this setup first.

- `.github/workflows/fork-pr-upstream.yml`

1. In your fork, go to `Settings -> Secrets and variables -> Actions`.
2. Add a secret named `UPSTREAM_PR_TOKEN`.
3. Use a token from your own GitHub account with permission to open pull requests on `niklas-olsson/keystone-polyphony`.
4. Choose a token type that can open upstream PRs.
5. Option A (recommended for most external contributors): classic PAT with `public_repo`.
6. Option B (only when your account can be granted repo access): fine-grained token targeting `niklas-olsson/keystone-polyphony` with `Pull requests: Read and write` and `Contents: Read`.
7. If fine-grained token setup cannot target the upstream repo, use Option A or use the manual PR path.
8. Trigger `Auto-PR to Upstream` once with `workflow_dispatch` to validate setup.

Without `UPSTREAM_PR_TOKEN`, the workflow intentionally skips PR creation. This is expected behavior and protects contributors from accidental credential misuse.

## Upstream Sync Requirement (Before Upstream PR)

Before opening (or auto-opening) a PR to upstream, sync your fork `main` with upstream `main` and resolve conflicts locally.

1. Add upstream remote once: `git remote add upstream https://github.com/niklas-olsson/keystone-polyphony.git`
2. Fetch upstream: `git fetch upstream main`
3. Update your fork main: `git checkout main && git merge upstream/main`
4. Resolve conflicts, run tests, then push: `git push origin main`
5. The auto-PR workflow enforces this and skips PR creation until your fork `main` includes latest `upstream/main`.

## Standard Human Flow (No Token Required)

1. Fork this repo to your GitHub account.
2. Clone your fork and create a branch, for example: `feat/<short-topic>` or `fix/<short-topic>`.
3. Keep changes focused to one concern per PR.
4. Update docs when behavior or developer workflow changes.
5. Open a PR from your branch to upstream `main`.
6. Respond to review and update the same branch until merged.

## Token Ownership Rules

1. Each fork owner provides and manages their own `UPSTREAM_PR_TOKEN`.
2. Do not ask maintainers to share personal tokens.
3. Do not reuse tokens between users or organizations.
4. Revoke and rotate tokens immediately if exposure is suspected.

## PR Quality Bar

1. Explain what changed and why in the PR description.
2. Include test notes (what you ran, or why tests were not needed).
3. Avoid unrelated refactors in the same PR.

## Security Notes

1. Never commit secrets, personal tokens, or credentials.
2. Store tokens only in GitHub Actions secrets, never in source files.

## Need Help

Open a GitHub issue or discussion with:

1. What you are trying to do.
2. What you expected to happen.
3. What actually happened (including logs/screenshots when useful).
