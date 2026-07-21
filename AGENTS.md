# Repository Instructions

- Do not run formatting or linting manually; repository hooks already handle those checks.
- Use targeted tests for behavior verification when changing runtime or experiment code.
- FastAPI `TestClient` tests use AnyIO's cross-thread portal and hang inside the managed sandbox; run those targeted tests outside the sandbox when verification requires them.
