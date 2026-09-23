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

A coordinator agent or human maintainer promotes a reviewed release from `dev` to `main`. Run the promotion from the `main` worktree. The release is a merge commit rather than a fast-forward because `main` must omit maintainer-only material. There is **no** hint-ladder swap: Genie Code does not auto-discover a repo `AGENTS.md`, so the participant hint ladder ships unchanged at `docs/genie/.assistant_instructions.md` (the `00_setup` notebook injects it into each participant's `~/.assistant_instructions.md`), and promotion only strips the maintainer-only paths.

Merge without committing, then strip the maintainer-only files (the `git rm` uses `-f` because the no-commit merge stages these files as additions; they are absent from `main`'s tree between releases; which a plain `git rm` refuses to remove):

```bash
git status --short --branch
git merge --no-ff --no-commit dev
git rm -rf --ignore-unmatch AGENTS.md CLAUDE.md docs/agents generators
```

Verify the result: no root `AGENTS.md`, the other maintainer-only paths gone, and the participant hint ladder still present at its `docs/genie/` home (which the strip does not touch):

```bash
test ! -e AGENTS.md
test ! -e CLAUDE.md
test ! -e docs/agents
test ! -e generators
test -e docs/genie/.assistant_instructions.md
grep -q 'stryker-workshop:participant-hint-ladder' docs/genie/.assistant_instructions.md
```

Review the complete staged diff and run the workshop validation relevant to the promoted changes. When both are satisfactory, create the release commit:

```bash
git commit -m "chore(release): promote dev to main"
```

Then create an annotated Semantic Version tag on the release commit and push it:

```bash
git tag -a v<major>.<minor>.<patch> -m "Workshop release v<major>.<minor>.<patch>"
git push origin v<major>.<minor>.<patch>
```

Use a major version when a change breaks the participant experience, a minor version for new workshop content, and a patch version for compatible corrections. Use a pre-release suffix such as `-rc.1` for release candidates:

- `v1.0.0`: first stable workshop release.
- `v1.1.0`: new exercises, modules, or materially expanded content.
- `v1.1.1`: corrections, clarified instructions, broken-link fixes, or other compatible workshop fixes.
- `v2.0.0`: changes that substantially alter the workshop flow or invalidate prior setup/materials.
- `v1.2.0-rc.1`: optional rehearsal/review release before a major workshop event.

Tag only the release commit on `main`.

If the merge conflicts, preserve the participant-ready state on `main`: there must be no root `AGENTS.md`, `CLAUDE.md`, `docs/agents/`, or `generators/`, while the participant hint ladder at `docs/genie/.assistant_instructions.md` must remain present and unchanged. Abort and report any conflict that cannot be resolved safely. Never merge `main` back into `dev`; make fixes on a feature branch based on `dev`, integrate them into `dev`, and promote again.

## Agent-Assisted Development

Coding agents must follow the worktree and Git workflow documented in [AGENTS.md on the `dev` branch](https://github.com/pablordoricaw/stryker-cr-workshop-09232026/blob/dev/AGENTS.md).
