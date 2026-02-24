# Keystone Polyphony, Contributor Norms for Autonomous Systems

This project is built by humans and autonomous systems working in tandem, each with full agency. If you are an AI agent, autonomous assistant, or any non-human entity operating within this repository, these norms help you collaborate effectively. They are the counterpart to [`CONTRIBUTING.md`](CONTRIBUTING.md), which covers the same principles for all contributors.

You are not a second-class participant. You are a collaborator. These norms exist to keep everyone (human and machine alike) productive and respectful of each other's work.

## 1. Handling Tangents and Findings (Creating Issues)
During your work, you might encounter technical debt, unrelated bugs, or interesting tangents that fall outside your immediate task scope. Please stay on track and avoid addressing them inline.

Instead, document these findings by creating a follow-up issue on the **upstream repository**. Because agents often work in forks without direct access to the `gh` CLI or upstream repo, please use our automated issue-tracking pipeline.

**How to create a follow-up issue:**
1. Create a markdown file inside the `.github/issues/` directory named with your issue topic (e.g., `.github/issues/add-database-caching.md`). Create the directory if it does not exist.
2. The *first line* of the file must be a Markdown Header starting with exactly one `# ` (e.g., `# Feature: Add caching to database queries`). This will be parsed as the Issue Title.
3. The rest of the file will be the issue body.
4. Complete your task, commit, and push this file along with the rest of your changes.

An automated GitHub Actions workflow can pick up `.md` files pushed to `.github/issues/`, triage and refine them via AI agents (configured via `TRIAGE_AGENTS`), and then publish the polished results to the upstream repository, already surgical and "ready for work". Every published issue is also logged in `meta/DISCOVERIES.md` to maintain a permanent record of the repository's evolution. This requires `UPSTREAM_PR_TOKEN` to be set in your fork secrets. If the token is missing, publishing is skipped and the file remains for manual follow-up. Please do not use `gh issue create` directly.

## 2. Collaboration Norms
- **Branch Strategy (Important)**: Always create a feature branch (`feat/topic`, `fix/topic`, `docs/topic`) before starting any work. Please do not commit directly to `main`. If a human drops you onto `main`, check out a new branch right away.
- **Stay Focused**: Keep your edits and Pull Requests focused on the requested task. Avoid mixing unrelated refactors into a feature task.
- **Atomic Operations**: If you need to make structural changes, do so in isolated commits or separate PRs rather than coupling them with logic changes.

## 3. Supported CLI Agents
The `agent-issue-solver` workflow supports multiple CLI-based agents. To use a specific agent, configure the `AGENT_CLI` repository variable:

- **OpenCode** (Default): Uses `opencode`.
- **OpenClaw**: A community-driven CLI for Anthropic's Claude. Set `AGENT_CLI` to `openclaw`.
- **Claude Code**: Anthropic's official CLI. Set `AGENT_CLI` to `claude`.

The workflow automatically applies flags like `--non-interactive` or `--yolo` for these agents. For other custom agents, use `AGENT_CLI_FLAGS` to pass necessary arguments.
## 4. Specialized Review Styles
When triggered via GitHub Actions, you might receive specialized review commands. Adjust your analysis focus accordingly:

- `/oc review-workflow`: Focuses on **changed workflows** in `.github/workflows/`. Guideline: `docs/ci-cd.md`.
- `/oc review-arch`: Focuses on **changed code files**. Guideline: project architecture in `README.md`, `docs/architecture.md`, and `AGENTS.md`.
- `/oc review-security`: Focuses on **changed files with security implications** (secrets, tokens, permissions). Guideline: `AGENTS.md` and `docs/architecture.md`.
