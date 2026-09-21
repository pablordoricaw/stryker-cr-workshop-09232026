# Contributing

If you are taking the workshop, follow the instructions in [README.md](README.md). This document is for people developing or maintaining the workshop.

## Branching Strategy

- `main` contains the participant-ready workshop and is the default branch.
- `dev` is the development integration branch.
- Create feature branches from the latest `dev`.
- Open pull requests against `dev`, not `main`.
- A maintainer promotes reviewed releases from `dev` to `main`.

Keep each contribution focused, use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) for commit messages, and run the validation relevant to your changes before opening a pull request.

## Agent-Assisted Development

Coding agents must follow the worktree and Git workflow documented in [AGENTS.md on the `dev` branch](https://github.com/pablordoricaw/stryker-cr-workshop-09232026/blob/dev/AGENTS.md).
