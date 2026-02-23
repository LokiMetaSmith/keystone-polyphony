# Git Hooks Architecture for All Contributors

This document describes the design and interaction model for the git hooks in Keystone Polyphony.

## Philosophy

In a repository where humans, AI agents, and other autonomous systems collaborate side-by-side, guardrails must be:
- **Informative**: Clear feedback for any contributor to correct mistakes.
- **Machine-Readable**: Unambiguous error signals for automated systems.
- **Automated**: Auto-fix simple issues (like formatting) where possible to reduce friction.
- **Enforcing**: Prevent common mistakes like committing directly to `main`.

## Interaction Stories

The following stories illustrate how different contributor types interact with the hooks. Whether you are a human typing at a terminal or an agent making programmatic commits, the hooks behave identically.

### The Careful Contributor (Human)
Alice is a human developer. She creates a feature branch `feat/new-logic` and starts working.
She finishes her changes but forgets that she added some trailing spaces in her markdown files and left a small syntax error in a utility shell script.

1. **First Attempt**: Alice runs `git commit -m "add logic"`.
2. **Linter Catch**: The `pre-commit` hook runs. It detects the shell syntax error and stops the commit.
   - Alice sees: `[ERROR] Shell syntax error in scripts/utils.sh: line 12: syntax error...`
   - Alice thinks: "Oh, I missed a closing brace." She fixes it.
3. **Second Attempt**: Alice runs `git commit -m "add logic"` again.
4. **Auto-Fix**: The `pre-commit` hook runs again.
   - It detects trailing whitespace in `README.md`.
   - Instead of failing, it automatically strips the whitespace from the staged content.
   - Alice sees: `pre-commit: normalized whitespace in staged content.`
   - The commit succeeds.
5. **Pushing**: Alice runs `git push origin feat/new-logic`.
6. **Testing**: The `pre-push` hook runs `scripts/run-tests.sh`.
   - Tests pass. Alice sees: `Tests passed. Proceeding with push.`
   - The push completes successfully.

### The Accidental Shortcut
Bob is in a hurry and tries to commit a quick fix directly to `main`.
1. **The Block**: Bob runs `git commit -m "quick fix"`.
2. **The Message**: The `pre-commit` hook stops him immediately.
   - Bob sees: `[ERROR] Committing directly to 'main' is discouraged. Please use a feature branch.`
   - Bob realizes he should follow the process, creates a branch, and continues.

### The Autonomous Contributor (Agent)

An AI agent is assigned to a task. It follows the instructions in `AGENTS.md`.

1. **Branching**: The agent creates `fix/issue-123`.
2. **Implementation**: It modifies the code.
3. **Committing**: It runs `git commit`.
4. **Validation**: The hooks run silently if everything is correct. If there's an error, the agent receives a non-zero exit code and a clear `[ERROR]` message.
5. **Recovery**: Because the error message is clear, the agent can parse it, understand the violation (e.g., "shell syntax error"), fix its own code, and retry.

## Hook Implementation Details

### pre-commit
- **Branch Protection**: Blocks commits to `main` (override with `ALLOW_MAIN_COMMIT=1`).
- **Whitespace Normalization**: Automatically strips trailing whitespace and ensures EOF newline for `.md`, `.sh`, `.yml`, `.yaml`, `.txt`.
- **Linting**: Runs `bash -n` on staged `.sh` files.

### pre-push
- **Branch Protection**: Blocks pushing to `main` (override with `ALLOW_MAIN_PUSH=1`).
- **Testing**: Executes `scripts/run-tests.sh`.
