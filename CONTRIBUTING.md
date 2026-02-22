# Contributing to Keystone Polyphony

This guide is the fastest path to making useful contributions.

## Quick Start

1. Fork the repository.
2. Run `./scripts/install-hooks.sh` once per clone to install local git hooks.
3. Create a branch from `main`.
4. If you run autonomous agents, complete the token setup in `Agentic Default Flow` before launching them.
5. Make your changes and run relevant checks locally.
6. Open a pull request to `niklas-olsson/keystone-polyphony:main` or let the agentic workflow open it.

Manual PRs are always supported and require no token setup.

## Local Hooks (Recommended)

Install hooks:

```bash
./scripts/install-hooks.sh
```

Current hook coverage:

1. `pre-commit` strips trailing spaces/tabs from **staged content only** (`.md`, `.yml`, `.yaml`, `.txt`, `.sh`) — the working tree is never touched, so partial staging is safe.
2. `pre-commit` normalizes missing EOF newline for those files.
3. `pre-commit` runs `git diff --cached --check` and blocks commits if unresolved whitespace issues remain.

Prerequisites checked by the installer: `git`, `awk`, `mktemp`, `cmp`, `tail`.

## Agentic Default Flow (Required For Autonomous Runs)

If you want autonomous agents to submit upstream PRs without manual intervention, do this setup first.

- `.github/workflows/hourly-merge-main.yml`

1. In your fork, go to `Settings -> Secrets and variables -> Actions`.
2. Add a secret named `UPSTREAM_PR_TOKEN`.
3. Use a token from your own GitHub account with permission to open pull requests on `niklas-olsson/keystone-polyphony`.
4. Choose a token type that can open upstream PRs.
5. Option A (recommended for most external contributors): classic PAT with `public_repo`.
6. Option B (only when your account can be granted repo access): fine-grained token targeting `niklas-olsson/keystone-polyphony` with `Pull requests: Read and write` and `Contents: Read`.
7. If fine-grained token setup cannot target the upstream repo, use Option A or use the manual PR path.
8. Trigger `Hourly Test and Merge to Main` once with `workflow_dispatch` to validate setup.

Without `UPSTREAM_PR_TOKEN`, upstream PR creation is intentionally skipped. Tested promotion to your fork `main` still runs.

### Repository Variables

| Variable | Purpose | Default |
|---|---|---|
| `HOURLY_TEST_COMMAND` | The shell command run during hourly staging tests | `npm test` (if `package.json` exists) |
| `JULES_DAILY_TASKS` | Max issues assigned to Jules per rolling 24h window | No limit (0 or unset) |

Set these in **Settings → Secrets and variables → Actions → Variables**.

## Upstream Sync Requirement (Before Upstream PR)

Before opening (or auto-opening) a PR to upstream, sync your fork `main` with upstream `main` and resolve conflicts locally.

1. Add upstream remote once: `git remote add upstream https://github.com/niklas-olsson/keystone-polyphony.git`
2. Fetch upstream: `git fetch upstream main`
3. Update your fork main: `git checkout main && git merge upstream/main`
4. Resolve conflicts, run tests, then push: `git push origin main`
5. The hourly pipeline enforces this and skips upstream PR creation until your fork `main` includes latest `upstream/main`.

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
