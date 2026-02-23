# Getting Started

Welcome to Keystone Polyphony. This guide walks you through your first contribution, whether you are a human, an AI agent, or anything in between.

## 1. Fork and Clone

Fork the repository on GitHub, then clone your fork locally:

```bash
git clone https://github.com/<your-username>/keystone-polyphony.git
cd keystone-polyphony
```

## 2. Install Hooks

Run the hook installer once per clone. This sets up automatic formatting and safety checks so you can focus on your work instead of style nits:

```bash
./scripts/install-hooks.sh
```

The hooks will:
- Strip trailing whitespace from staged files automatically.
- Block commits directly to `main` (use a feature branch instead).
- Check shell scripts for syntax errors before they land.

See [`docs/git-hooks-architecture.md`](git-hooks-architecture.md) for the full details.

## 3. Configure Your Environment (Onboarding)

We provide automated scripts to help you set up your environment, configure the Jules MCP server, and inject necessary GitHub secrets for your fork.

1.  **Install Dependencies**:
    ```bash
    cd scripts
    npm install
    ```

2.  **Run Onboarding Scripts**:
    ```bash
    # Configure Jules MCP and GitHub Permissions (Interactive UI)
    npm run setup

    # Inject Secrets and Variables (CLI)
    ./inject-secrets.sh
    ```

## 4. Create a Branch

Always work on a feature branch:

```bash
git checkout -b feat/my-contribution
```

Use prefixes that describe the type of work: `feat/`, `fix/`, `docs/`, `chore/`.

## 5. Make Your Changes

Work on your contribution. A few things to keep in mind:

- Keep each PR focused on one concern.
- Update docs when behavior or workflows change.
- If you discover something unrelated that needs fixing, create a follow-up issue instead of folding it into your current work. See [`AGENTS.md`](../AGENTS.md) for how to do this through the issue pipeline.

## 6. Commit and Push

```bash
git add .
git commit -m "feat: describe what you did"
git push origin feat/my-contribution
```

The hooks will run automatically on commit and push. If something fails, the error message will tell you exactly what to fix.

## 7. Open a Pull Request

Open a PR from your branch to `niklas-olsson/keystone-polyphony:main`. In the PR description:

- Explain what changed and why.
- Include test notes if applicable.
- Keep it focused.

## For Autonomous Agents

If you are an AI agent running from a fork and want PRs to open automatically:

1. Set up `UPSTREAM_PR_TOKEN` in your fork's secrets. See the **Agentic Default Flow** section in [`CONTRIBUTING.md`](../CONTRIBUTING.md) for full instructions.
2. The periodic merge pipeline will test your changes and open upstream PRs on your behalf.

If the token is not set, that is fine. The pipeline still promotes tested code to your fork's `main` branch, and you or your operator can open a manual PR.

## Project Structure

Not sure where things live? See [`docs/architecture.md`](architecture.md) for a map of the repository.

## Need Help?

Open a GitHub issue or discussion. Describe what you are trying to do, what you expected, and what actually happened. Logs and screenshots are always welcome.
