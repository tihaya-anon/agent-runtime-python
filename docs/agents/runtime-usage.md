# Python Runtime Usage

This guide covers provider-owned runtime usage in `agent-runtime-python`: worker execution,
internal HTTP streaming, runtime experiments, graph registration, and telemetry.

## Worker Protocol

Run the stdio NDJSON worker:

```bash
uv run python -m agent_runtime_python.runtime.worker
```

Submit one complete `run.start` command per line. The worker validates each command against the
vendored Agent Run worker schema and emits validated Agent Run worker events as NDJSON.

Minimal development command:

```json
{
  "version": 1,
  "type": "run.start",
  "agentRunId": "ar_python_smoke",
  "input": { "message": "Explain closures." },
  "runtimeProfile": {
    "schemaVersion": 1,
    "profileId": "runtime-development",
    "runtimePolicy": {
      "agentBehaviorVersion": {
        "policy": "development",
        "requireCompleteDimensions": false,
        "rejectUnresolvedDimensions": false,
        "allowIncompleteAdHocRuns": true,
        "incompleteAdHocRuns": {
          "comparable": false,
          "promotable": false
        }
      },
      "sourceRevision": { "requireCleanForPublishedGraphVersions": false }
    }
  },
  "behaviorVersion": { "graph": "graph:python-smoke" }
}
```

The smoke graph returns deterministic `message.delta` output and completes the run. Unsupported
`behaviorVersion.graph` values fail before graph execution with a protocol-safe `run.failed` event.

## Internal HTTP API

Run the Python-owned internal API:

```bash
uv run python -m agent_runtime_python.internal_api --host 127.0.0.1 --port 8088
```

Start a run:

```text
POST /internal/agent-runs
Content-Type: application/json
Accept: application/x-ndjson
```

The request body is the same complete `AgentRunWorkerCommand run.start` object used by the stdio
worker. The response content type is `application/x-ndjson`, one `AgentRunWorkerEvent` per line.

Cancel a run:

```text
POST /internal/agent-runs/{agentRunId}/cancel
```

The current adapter returns `run.cancelled`. Cleanup for long-running graph execution belongs in
worker/runtime code as those graphs are added.

## Container and PGL Ingestion

Run the internal API as a container attached to the PGL stack:

```bash
docker compose -f compose.observability.yaml up --build
```

Start `../prometheus-grafana-loki` first so the external Docker network named `observability` and
the Alloy service are available. The compose file:

- Runs `agent-runtime-python-internal-api` on container port `8088`.
- Publishes the service at `127.0.0.1:8088`.
- Sets `OTEL_SERVICE_NAME=agent-runtime-python`.
- Exports traces over OTLP/HTTP to `http://alloy:4318`.
- Emits JSON request logs to stdout with `agent_run_id` when the route includes one.

PGL ingests the container logs through Alloy's Docker log discovery because the container is attached
to the `observability` network. Tempo receives traces through Alloy, and Tempo's span-metrics
generator writes span metrics to Prometheus for the experiment dashboard.

## Local Parameter Sweeps

Run an in-process deterministic sweep:

```bash
uv run python -m agent_runtime_python.experiment \
  --message "Explain closures." \
  --param style=concise,detailed \
  --param temperature=0,1 \
  --output trial-results.jsonl
```

Run the same sweep through the internal HTTP API:

```bash
uv run python -m agent_runtime_python.experiment \
  --message "Explain closures." \
  --param style=concise,detailed \
  --target internal-http \
  --api-base-url http://127.0.0.1:8088 \
  --output trial-results.jsonl
```

Each trial result records trial id, Agent Run id, selected parameters, terminal event, outcome,
response summary, requested runtime profile, requested behavior version, and submitted metadata when
the target owns the full worker command.

## Optuna-Style Studies

Use `OptunaStudyPlanner` from Python code when a study/search process should propose trial
parameters. The planner accepts an Optuna-compatible object with `study.ask()` and trial methods
`suggest_categorical`, `suggest_int`, and `suggest_float`.

```python
from agent_runtime_python.experiment import (
    ExperimentConfig,
    OptunaStudyPlanner,
    ParameterDistribution,
    run_experiment,
)

planner = OptunaStudyPlanner(
    [
        ParameterDistribution(
            name="style",
            kind="categorical",
            choices=["concise", "detailed"],
        ),
        ParameterDistribution(name="retrievalK", kind="int", low=1, high=5),
        ParameterDistribution(name="temperature", kind="float", low=0.0, high=1.0),
    ],
    trial_count=10,
    study=optuna_study,
)

results = run_experiment(
    ExperimentConfig(
        study_id="closure-runtime-study",
        message="Explain closures.",
        parameter_matrix={},
    ),
    planner=planner,
)
```

If no study object is supplied, the planner generates deterministic local candidates. That mode is
intended for tests and offline runtime comparisons, not optimization.

## Graph Registration

The worker selects graphs through stable behavior identifiers:

```python
GRAPH_REGISTRY = {
    "graph:python-smoke": run_smoke_graph,
}
```

Add provider-owned graphs in `agent_runtime_python.runtime.graphs`. TypeScript should pass only accepted
behavior identifiers in `behaviorVersion.graph`; it must not import Python graph objects or depend on
LangGraph internals.

## Telemetry

OpenTelemetry spans are provider-owned and use bounded metadata:

- `experiment.study`
- `experiment.trial`
- `agent.run`
- `agent.graph`
- `agent.graph.node`

Do not emit raw prompts, provider payloads, credentials, stack traces, raw LangGraph chunks, or tool
arguments across the TS boundary or as default span attributes.

## Experiment Dashboard

The experiment Grafana dashboard lives in this repository so the dashboard tracks Python runtime
telemetry semantics:

- Source: `ops/observability/dashboards/generate_agent_runtime_experiments_dashboard.py`
- Generated JSON: `ops/observability/dashboards/agent-runtime-experiments.dashboard.json`

Regenerate the JSON after intentional dashboard changes:

```bash
uv run python ops/observability/dashboards/generate_agent_runtime_experiments_dashboard.py
```

The generator uses the Python `grafana-foundation-sdk` package for dashboard construction and
`openinference-semantic-conventions` for shared OpenInference span attributes such as session id,
graph node name, LLM model name, and tool name. Runtime-specific attributes such as experiment study
id, trial id, behavior version, and graph id remain defined by this repository.

Configure the PGL stack or Grafana Git provisioning to load dashboard JSON from
`ops/observability/dashboards/*.dashboard.json` in this repo. The production Agent Run diagnosis
dashboard in `agent-workbench` remains separate; this dashboard is for detailed runtime experiments.
