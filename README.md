# agent-runtime-python

Python LangGraph runtime and experiment tooling for Agent Run workers.

## Ownership

This repository owns Python-side LangGraph execution and experiment performance. It consumes the
Agent Run worker protocol from `tihaya-anon/agent-workbench` and emits protocol-compliant worker
events back to the TypeScript gateway.

`agent-workbench` remains the owner of the TypeScript web/API control plane, canonical protocol
schemas, and browser-facing Agent Run stream.

## Local Development

Use Python 3.12 or newer.

```bash
uv sync
uv run python -m unittest discover -s tests
uv run python -m agent_runtime_python.worker
```

The worker entry point reads Agent Run worker protocol commands as NDJSON from stdin and emits
protocol-compliant worker events as NDJSON on stdout. The current graph is a deterministic LangGraph
smoke graph. Full production graph execution, cancellation cleanup for long-running runs, and
telemetry are tracked from `agent-workbench` migration issues.

## Protocol

Canonical protocol source lives in `agent-workbench`:

- `packages/shared/src/schemas/agent-run-worker.ts`
- `packages/shared/json-schema/agent-run-worker-command.schema.json`
- `packages/shared/json-schema/agent-run-worker-event.schema.json`

The JSON Schema artifacts are vendored under `src/agent_runtime_python/schemas/` for local
validation. Refresh them from `agent-workbench` when the protocol changes.
