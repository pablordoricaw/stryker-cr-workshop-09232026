# Contributing

If you are taking the workshop, follow the instructions in [README.md](README.md). This document is for people developing or maintaining the workshop.

## Branching Strategy

- `main` contains the participant-ready workshop and is the default branch.
- `dev` is the development integration branch.
- Create feature branches from the latest `dev`.
- Open pull requests against `dev`, not `main`.
- A coordinator agent or human maintainer promotes reviewed releases from `dev` to `main`.

Keep each contribution focused, use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) for commit messages, and run the validation relevant to your changes before opening a pull request.

## Promote a Workshop Release

A coordinator agent or human maintainer promotes a reviewed release from `dev` to `main`. Run the promotion from the `main` worktree. The release is a merge commit rather than a fast-forward because `main` must omit maintainer-only material.

```bash
git status --short --branch
git merge --no-ff --no-commit dev
git rm -r --ignore-unmatch AGENTS.md CLAUDE.md docs/agents generators
test ! -e AGENTS.md
test ! -e CLAUDE.md
test ! -e docs/agents
test ! -e generators
```

Review the complete staged diff and run the workshop validation relevant to the promoted changes. When both are satisfactory, create the release commit:

```bash
git commit -m "chore(release): promote dev to main"
```

If the merge conflicts, preserve the participant-ready state on `main`: `AGENTS.md`, `CLAUDE.md`, `docs/agents/`, and `generators/` must remain absent. Abort and report any conflict that cannot be resolved safely. Never merge `main` back into `dev`; make fixes on a feature branch based on `dev`, integrate them into `dev`, and promote again. Create release tags from `main` only.

## Agent-Assisted Development

Coding agents must follow the worktree and Git workflow documented in [AGENTS.md on the `dev` branch](https://github.com/pablordoricaw/stryker-cr-workshop-09232026/blob/dev/AGENTS.md).
