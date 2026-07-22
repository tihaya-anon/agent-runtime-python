# Repository Instructions

- Do not run formatting or linting manually; repository hooks already handle those checks.
- Use targeted tests for behavior verification when changing runtime or experiment code.
- FastAPI `TestClient` tests use AnyIO's cross-thread portal and hang inside the managed sandbox; run those targeted tests outside the sandbox when verification requires them.

## Agent skills

### Issue tracker

Issues and PRDs for this repo live as GitHub issues. See `docs/agents/issue-tracker.md`.

### Triage labels

The repo uses the default canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo with `CONTEXT.md` and `docs/adr/` at the root. See `docs/agents/domain.md`.
