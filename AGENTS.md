# Keystone Polyphony - Agent Instructions

If you are an AI agent or autonomous assistant operating within this repository, follow these core guidelines to ensure productive collaboration.

## 1. Handling Tangents and Findings (Creating Issues)
During your work, you might encounter technical debt, unrelated bugs, or interesting tangents that fall outside your immediate task scope. **Do not deviate from your current task to address them.** 

Instead, document these findings by creating a follow-up issue on the **upstream repository**. Because agents often work in forks without direct access to the `gh` CLI or upstream repo, you must use our automated issue-tracking pipeline.

**How to create a follow-up issue:**
1. Create a markdown file inside the `.github/issues/` directory named with your issue topic (e.g., `.github/issues/add-database-caching.md`). Create the directory if it does not exist.
2. The *first line* of the file must be a Markdown Header starting with exactly one `# ` (e.g., `# Feature: Add caching to database queries`). This will be parsed as the Issue Title.
3. The rest of the file will be the issue body. 
4. Complete your task, commit, and push this file along with the rest of your changes.

An automated GitHub Actions workflow can pick up `.md` files pushed to `.github/issues/`, publish them to the upstream repository, and then commit removal of the file from your branch. Every published issue is also logged in `meta/DISCOVERIES.md` to maintain a permanent record of the repository's evolution. This requires `UPSTREAM_PR_TOKEN` to be set in your fork secrets. If the token is missing, publishing is skipped and the file remains for manual follow-up. Do not attempt to use `gh issue create`.

## 2. Scope Constraints
- **Branch Strategy (CRITICAL)**: Always create a feature branch (`feat/topic`, `fix/topic`, `docs/topic`) before starting any work. **Never commit directly to `main`**. If a human drops you onto `main`, immediately check out a new branch.
- **Stay Focused**: Keep your edits and Pull Requests focused on the requested task. Do not mix unrelated refactors into a feature task.
- **Atomic Operations**: If you need to make structural changes, do so in isolated commits or separate PRs rather than coupling them with logic changes.
