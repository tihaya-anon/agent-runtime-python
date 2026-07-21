---
name: conventional-commits
description: Conventional Commit workflow for code changes. Use when Codex is asked to commit code, prepare a commit message, finish an implementation, or decide whether completed repository changes are ready to commit. Enforces Conventional Commit message format, prerequisite checks, and commits changes once formatting, linting, and relevant tests or type checks are satisfied.
---

# Conventional Commits

## Overview

Use this skill to finish code changes with a clear Conventional Commit. Treat committing as part of the implementation workflow: once the requested change is complete and the relevant prerequisites are satisfied, create the commit instead of leaving the work uncommitted.

## Commit Readiness

Before committing, verify the work is ready:

- Inspect `git status --short` and `git diff` to understand exactly what will be committed.
- Include only changes that are part of the user-requested work. Do not stage unrelated user changes.
- Run the targeted tests, type checks, or builds needed for the change. If repository hooks handle formatting or linting, treat those prerequisites as satisfied unless a hook reports a failure.
- Do not manually run formatting or linting when repository instructions say hooks own those checks.
- If verification cannot be run, explain why and do not claim it passed.
- Commit once the change is complete and the relevant checks have passed or are already covered by hooks.

## Message Format

Use this structure:

```text
<type>[optional scope][optional !]: <description>

[optional body]

[optional footer(s)]
```

Use a lowercase type and an imperative, present-tense description. Keep the subject concise, specific, and under about 72 characters when practical.

Common types:

- `feat`: introduce user-facing behavior or capability
- `fix`: correct a bug or broken behavior
- `docs`: documentation-only changes
- `test`: add or update tests without production behavior changes
- `refactor`: restructure code without intended behavior changes
- `perf`: improve performance
- `style`: formatting or whitespace-only changes
- `build`: build system, dependency, or packaging changes
- `ci`: CI configuration or workflow changes
- `chore`: maintenance that does not fit another type
- `revert`: revert a previous commit

Use a scope when it materially clarifies the affected area, such as `feat(api): add lesson routes` or `fix(web): preserve chat input`.

Use `!` or a `BREAKING CHANGE:` footer for breaking changes:

```text
feat(api)!: require authenticated lesson creation

BREAKING CHANGE: unauthenticated lesson creation now returns 401.
```

## Commit Workflow

1. Review the final diff and choose the narrowest accurate type and optional scope.
2. Stage only the intended files.
3. Create the commit with `git commit -m "<type>(<scope>): <description>"` for simple changes.
4. Use a body when the rationale, migration notes, or non-obvious behavior would help future readers.
5. Report the commit hash, message, and verification commands in the final response.

## Examples

```text
feat(web): add lesson search filters
fix(api): reject empty lesson titles
test(agent): cover retry fallback
docs: document database setup
chore(deps): update vite
```

## Guardrails

- Do not commit when tests fail, when the diff contains unresolved conflict markers, or when the requested work is incomplete.
- Do not amend, squash, rebase, force-push, or alter existing commits unless the user explicitly asks.
- If hooks fail during commit, fix the failure when it is in scope, rerun the relevant verification, and commit again.
- If unrelated changes are present, leave them unstaged and mention them separately.
