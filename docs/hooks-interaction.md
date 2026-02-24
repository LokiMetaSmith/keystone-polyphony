# Human Interaction Story: Git Hooks

This document outlines the expected interaction flow for a human contributor working with the Keystone Polyphony repository and its git hooks.

## Scenario: Fixing a Bug

**Role:** Human Contributor (`Alice`)

**Goal:** Fix a bug in the Python codebase.

### 1. Setup
Alice clones the repository and runs the onboarding script:
```bash
./scripts/install-hooks.sh
```
This installs the local git hooks (`pre-commit` and `pre-push`).

### 2. Making Changes
Alice creates a new branch `fix/bug-123` and modifies `src/liminal_bridge/server.py`. She introduces a fix but accidentally leaves a syntax error (a missing colon) and forgets to format the file with `black`.

### 3. Attempting to Commit (Failure Case)
Alice stages her changes and runs:
```bash
git commit -m "Fix bug in server logic"
```

**Outcome:** The commit is **blocked**.
Alice sees the following output in her terminal:

```
[ERROR] python syntax check failed.
  File "src/liminal_bridge/server.py", line 45
    def handle_request(req)
                          ^
SyntaxError: expected ':'

[ACTION REQUIRED] Please fix the syntax error above.
```

Alice realizes her mistake, adds the colon, and tries again.

### 4. Attempting to Commit (Linting/Formatting Check)
Alice fixes the syntax error but still hasn't formatted the file. She stages the file again and commits.

**Outcome:** The commit is **blocked** again.
Alice sees:

```
[ERROR] code formatting check failed.
would reformat src/liminal_bridge/server.py

[ACTION REQUIRED] Run the following command to fix formatting issues:
  black .
```

Alice appreciates the clear instruction. She runs `black .`, which automatically formats her code. She stages the changes again.

### 5. Successful Commit
Alice runs `git commit` again.
**Outcome:** Success! The hooks verify that syntax is correct and formatting is compliant. The commit is created.

### 6. Pushing Changes
Alice pushes her branch:
```bash
git push origin fix/bug-123
```

**Outcome:** The `pre-push` hook triggers.
Alice sees:
```
>>> Running repository health checks...
Checking shell scripts syntax...
Checking python code quality...
Running tests...
>>> All checks passed!
Pushed fix/bug-123 to origin.
```

### Summary
The experience is designed to be **informative and actionable**. Instead of cryptic error codes, Alice receives specific instructions (`Run black .`, `SyntaxError at line 45`). This prevents frustration and ensures that only high-quality code enters the repository history, saving time for reviewers (both human and AI).
