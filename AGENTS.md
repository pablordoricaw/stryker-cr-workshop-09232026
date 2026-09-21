# Repository Agent Workflow

This repository is developed with multiple coding agents using Git worktrees. Follow these rules for every task.

## Before Making Changes

1. Run `git status --short --branch` and confirm the current worktree and branch.
2. Work only in the worktree and branch assigned to you.
3. Do not make feature changes in the `main` worktree. The `main` worktree is reserved for review and integration.
4. If you are on `main` and the task requires code or content changes, stop and ask the coordinator for a feature worktree.
5. Inspect existing changes before editing. Treat changes you did not create as user or agent work and preserve them.

## Worktree and Branch Ownership

- Use one dedicated worktree and one dedicated feature branch per agent task.
- Use descriptive branch names that identify the agent and task, such as `codex/add-exercises`, `claude/update-docs`, or `cursor/fix-validation`.
- Never use the same branch in more than one worktree.
- Do not switch branches inside an assigned worktree.
- Do not create, move, lock, unlock, prune, or remove worktrees unless you are the coordinating agent or the user explicitly asks you to.
- Do not modify files inside the bare repository or its internal `worktrees/` metadata directory.

## Making Changes

- Keep each task focused. Do not alter unrelated files or reformat unrelated code.
- Do not discard or overwrite existing work to make your task easier.
- Never run destructive commands such as `git reset --hard`, `git clean`, or `git checkout -- <path>` unless the user explicitly requests the exact operation.
- Commit only changes that belong to your task. Review `git diff` and `git diff --staged` before committing.
- Write clear, focused commit messages. Split unrelated changes into separate commits.

## Commit Messages

All commit messages must follow the [Conventional Commits v1.0.0 specification](https://www.conventionalcommits.org/en/v1.0.0/#specification). Use the form `<type>[optional scope][optional !]: <description>`, with an optional body and footers. Use `feat` for new features and `fix` for bug fixes. Mark breaking changes with `!` before the colon or a `BREAKING CHANGE:` footer.

## Linear History

The repository maintains a linear history. Feature branches are rebased onto `main`, and integration is fast-forward only.

### Update a feature branch

Before handoff, rebase the feature branch onto the current local `main`:

```bash
git status --short
git rebase main
```

The worktree must be clean before rebasing. If `main` needs to be refreshed from the remote, the coordinating agent must first update it in the main worktree using a fast-forward-only operation.

If the rebase has conflicts:

1. Resolve conflicts in the feature worktree without discarding either side blindly.
2. Stage the resolved files with `git add`.
3. Continue with `git rebase --continue`.
4. Run the relevant validation again after the rebase.

Use `git rebase --abort` if the conflict cannot be resolved safely, then report the blocker. Do not merge `main` into the feature branch.

Because rebase rewrites commit IDs, a previously published feature branch may only be updated with `git push --force-with-lease`. Never force-push `main`, and never force-push another agent's branch.

### Integrate a completed branch

Only the coordinating agent integrates feature branches. In the main worktree:

```bash
git status --short --branch
git merge --ff-only <feature-branch>
```

`git merge --ff-only` is allowed solely to advance `main` without creating a merge commit. Do not use a regular merge, create a merge commit, or use a three-way merge to integrate a feature branch.

If fast-forward integration fails, do not override it. Return the feature branch to its owner, rebase it onto the latest `main`, validate it, and retry `git merge --ff-only`.

## Validation and Handoff

- Run the tests, linters, formatters, and build checks relevant to the changed files. Follow repository-specific commands documented in the README or project configuration.
- If a check cannot be run, state which check was skipped and why.
- Leave the worktree clean at handoff unless the user explicitly asks for uncommitted changes.
- Report the worktree path, branch name, commit IDs, validation performed, and any remaining risks or unresolved issues.
- Do not merge the branch, remove its worktree, or delete its branch as part of handoff. The coordinating agent performs those steps after review.
