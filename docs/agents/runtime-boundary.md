# Python Runtime Boundary

Status: active guidance.

`agent-runtime-python` owns LangGraph runtime behavior. It should not own product-path
measurement through the TypeScript API gateway.

## Runtime Ownership

This repository owns:

- Python-defined LangGraph graphs, nodes, tools, prompts, and runtime registries.
- Worker-side mapping from LangGraph streams into Agent Run worker events.
- Runtime protocol validation from the Python side.
- Direct runtime experiments such as parameter sweeps, graph variants, and Optuna-style studies.
- Runtime-internal telemetry for graph, node, model, tool, and retrieval execution.

This repository does not own:

- Browser-facing API routes.
- Product Agent Run stream compatibility.
- TypeScript Runtime Profile selection or behavior-version acceptance policy.
- End-to-end product-path measurement through `POST /api/agent-runs`.
- Test harnesses that require the TS API, frontend stream consumer, or observability stack.

## TypeScript Integration

The TypeScript gateway should call Python through a language-neutral internal runtime protocol.
The current stdio NDJSON worker protocol is the first transport. If the boundary becomes a
long-running service, promote the same command and event shapes to an internal HTTP streaming API.

Recommended future service shape:

```text
POST /internal/agent-runs
Content-Type: application/json
Accept: application/x-ndjson

AgentRunWorkerCommand run.start

200 OK
Content-Type: application/x-ndjson

AgentRunWorkerEvent lines
```

The Python provider now includes a stdlib HTTP adapter for that boundary:

```bash
uv run python -m agent_runtime_python.internal_api --host 127.0.0.1 --port 8088
```

The handler is intentionally thin. It accepts a complete `AgentRunWorkerCommand run.start`,
delegates to the worker, and streams only validated `AgentRunWorkerEvent` NDJSON lines.

Cancellation should be explicit:

```text
POST /internal/agent-runs/{agentRunId}/cancel
```

The current adapter returns a protocol `run.cancelled` event for the cancel route. Long-running graph
cancellation cleanup still belongs in worker/runtime execution code.

The TS gateway assigns `agentRunId`, resolves Runtime Profile and Agent Behavior Version acceptance,
then passes the accepted command to Python. Python selects and runs the registered graph.

## Graph Selection

TS must not import Python graph objects or know LangGraph implementation details. Graph selection
should happen through stable behavior identifiers in the accepted worker command, such as
`behaviorVersion.graph`.

Python should map those identifiers to local graph builders:

```python
GRAPH_REGISTRY = {
    "graph:tutor:v1": build_tutor_graph,
    "graph:assessor:v1": build_assessor_graph,
}
```

Unsupported graph identifiers should fail before graph execution with a protocol-safe
`run.failed` event.

The initial registry lives in `agent_runtime_python.graphs` and maps `graph:python-smoke` to the
deterministic LangGraph smoke graph. New provider-owned graphs should be added there behind stable
behavior identifiers.

## Experiment Scope

Python experiments should target Python runtime behavior directly. Prefer in-process or worker
protocol targets that submit full worker commands and record protocol events.

Provider-owned experiment APIs are:

- `ParameterSweepPlanner` for deterministic exhaustive parameter matrices.
- `OptunaStudyPlanner` for Optuna-compatible search spaces. It accepts an object with `study.ask()`
  and trials with `suggest_categorical`, `suggest_int`, and `suggest_float`; without a study object
  it produces deterministic candidates for local tests.
- `DirectWorkerTarget` for in-process worker protocol execution.
- `InternalHttpStreamingTarget` for `POST /internal/agent-runs` NDJSON streaming.

Do not add new experiment targets that call the TS product API. Whole-product path checks belong in
`agent-workbench` acceptance tests or separate test/observability engineering. The existing
`TsGatewayTarget` is a migration convenience and should be moved out of this repository or retired
when the TS side owns equivalent integration coverage.

## Telemetry Design

OpenTelemetry spans should follow these provider-owned boundaries:

- `experiment.study`: one runtime study, tagged with study id and target.
- `experiment.trial`: one trial command, tagged with trial id, target, selected parameters, and
  outcome.
- `agent.run`: one accepted worker command, tagged with Agent Run id, runtime profile id, accepted
  behavior-version dimensions, outcome, and protocol-safe error classification.
- `agent.graph`: registered graph execution, tagged with graph id.
- `agent.graph.node`: LangGraph node execution, tagged with graph id and node name.

Use bounded metadata only. Raw LangGraph chunks, prompts, provider request/response bodies, stack
traces, credentials, and tool arguments must stay out of boundary events and default span
attributes.

## Event Safety

Python must emit only Agent Run worker events across the boundary. It must not expose raw LangGraph
chunks, prompts, provider payloads, stack traces, credentials, or tool arguments to TS. Diagnostic
details belong in telemetry with bounded, product-safe metadata.
