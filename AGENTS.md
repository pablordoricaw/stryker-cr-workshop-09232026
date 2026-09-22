# Repository Agent Workflow

This repository is developed with multiple coding agents using Git worktrees. Follow these rules for every task.

## Branch Roles

- `dev` is the development integration branch. All feature work starts from and returns to `dev`.
- `main` is the participant-ready release branch and the remote default branch. It must not contain the **maintainer** `AGENTS.md` (the worktree/Git workflow documented in this file), `CLAUDE.md`, the `docs/agents/` skill configuration, or other maintainer-only material. Its root `AGENTS.md` is instead the **participant hint ladder** — authored on `dev` at `docs/participant/AGENTS.md` and swapped to the root at release so Genie Code auto-discovers it via its directory-tree walk.
- Feature branches use one dedicated worktree per agent task.
- `worktrees/dev/` and `worktrees/main/` are reserved for coordination, review, and integration. Do not make feature changes directly in either worktree.

The maintainer agent instructions live on `dev`, so workshop participants who clone the default `main` branch receive only workshop material — with the participant hint ladder as the root `AGENTS.md`.

## Before Making Changes

1. Run `git status --short --branch` and confirm the current worktree and branch.
2. Work only in the worktree and branch assigned to you.
3. Confirm that the feature branch is based on `dev`, not `main`.
4. If you are on `dev` or `main` and the task requires code or workshop-content changes, stop and ask the coordinator for a feature worktree.
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

## Feature Branch History

Feature development maintains a linear history. Feature branches are rebased onto `dev`, and the coordinator integrates them into `dev` using fast-forward-only merges.

### Update a feature branch

Before handoff, rebase the feature branch onto the current local `dev`:

```bash
git status --short
git rebase dev
```

The worktree must be clean before rebasing. If `dev` needs to be refreshed from the remote, the coordinating agent must first update it in the dev worktree using a fast-forward-only operation.

If the rebase has conflicts:

1. Resolve conflicts in the feature worktree without discarding either side blindly.
2. Stage the resolved files with `git add`.
3. Continue with `git rebase --continue`.
4. Run the relevant validation again after the rebase.

Use `git rebase --abort` if the conflict cannot be resolved safely, then report the blocker. Do not merge `dev` into the feature branch.

Because rebase rewrites commit IDs, a previously published feature branch may only be updated with `git push --force-with-lease`. Never force-push `dev` or `main`, and never force-push another agent's branch.

### Integrate a completed feature

Only the coordinating agent integrates feature branches. In the dev worktree:

```bash
git status --short --branch
git merge --ff-only <feature-branch>
```

Do not use a regular merge or create a merge commit when integrating a feature into `dev`. If fast-forward integration fails, return the feature branch to its owner to rebase onto the latest `dev`, validate it, and retry.

## Promote a Workshop Release

The coordinating agent or a human maintainer may promote `dev` to `main`. Release promotion is intentionally different from feature integration: `main` omits the maintainer-only files **and swaps in the participant hint ladder** as its root `AGENTS.md`, so promotion uses a merge commit rather than a fast-forward merge.

From the main worktree, merge without committing, strip the maintainer-only files, then move the participant hint ladder into the root as `AGENTS.md`:

```bash
git status --short --branch
git merge --no-ff --no-commit dev
git rm -rf --ignore-unmatch AGENTS.md CLAUDE.md docs/agents generators
git mv docs/participant/AGENTS.md AGENTS.md
```

The `git rm` uses `-f` because the no-commit merge stages these files as additions (they are absent from `main`'s tree between releases), which a plain `git rm` refuses to remove. It drops the maintainer `AGENTS.md`; the `git mv` then puts the participant hint ladder in its place. Verify the swap before committing — the root `AGENTS.md` must now exist and be the participant hint ladder (its sentinel present, the maintainer workflow's title absent), the participant source must no longer sit under `docs/`, and the other maintainer-only paths must be gone:

```bash
test -e AGENTS.md
grep -q 'stryker-workshop:participant-hint-ladder' AGENTS.md
! grep -q 'Repository Agent Workflow' AGENTS.md
test ! -e docs/participant/AGENTS.md
test ! -e CLAUDE.md
test ! -e docs/agents
test ! -e generators
git commit -m "chore(release): promote dev to main"
```

Before committing the release merge, review the complete staged diff and run the workshop validation relevant to the promoted changes. After committing, create an annotated Semantic Version tag on that `main` commit and push the tag:

```bash
git tag -a v<major>.<minor>.<patch> -m "Workshop release v<major>.<minor>.<patch>"
git push origin v<major>.<minor>.<patch>
```

Use a major version for participant-breaking changes, a minor version for new workshop content, and a patch version for compatible corrections. Use a pre-release suffix such as `-rc.1` for release candidates:

- `v1.0.0` — first stable workshop release.
- `v1.1.0` — new exercises, modules, or materially expanded content.
- `v1.1.1` — corrections, clarified instructions, broken-link fixes, or other compatible workshop fixes.
- `v2.0.0` — changes that substantially alter the workshop flow or invalidate prior setup/materials.
- `v1.2.0-rc.1` — optional rehearsal/review release before a major workshop event.

If the merge conflicts, preserve the participant-ready state on `main`; in particular, the root `AGENTS.md` must end up as the **participant hint ladder** (not the maintainer workflow), while `CLAUDE.md`, `docs/agents/`, `generators/`, and the `docs/participant/AGENTS.md` source must be absent. Abort the merge and report the blocker if any conflict cannot be resolved safely.

Do not merge `main` back into `dev`, because doing so would carry the release-only deletion of the agent instructions into development. Apply fixes on a feature branch based on `dev`, integrate them into `dev`, and promote again. Create release tags from `main` only.

## Validation and Handoff

- Run the tests, linters, formatters, and build checks relevant to the changed files. Follow repository-specific commands documented in the README or project configuration.
- If a check cannot be run, state which check was skipped and why.
- Leave the worktree clean at handoff unless the user explicitly asks for uncommitted changes.
- Report the worktree path, branch name, commit IDs, validation performed, and any remaining risks or unresolved issues.
- Do not merge the branch, remove its worktree, or delete its branch as part of handoff. The coordinating agent performs those steps after review.
