# Codebase Overview

This repository contains a Python Agent Run runtime, experiment runner, and observability tooling for
LangGraph-backed agent development trials.

## Main Surfaces

- `agent_runtime_python.runtime.worker` runs the NDJSON worker protocol and executes registered
  graphs.
- `agent_runtime_python.experiment` is the public experiment interface and CLI entry point.
- `agent_runtime_python.internal_api` starts the FastAPI internal API for streaming Agent Run events.
- `agent_runtime_python.observability.telemetry` exposes the public telemetry interface.

## Runtime Flow

The worker accepts one protocol command at a time, validates it against the JSON schemas in
`src/agent_runtime_python/schemas/`, runs the requested graph, and returns protocol events. Runtime
graph lookup lives in `runtime/graphs.py`; the deterministic smoke graphs live in
`runtime/smoke_graph.py`.

## Experiment Modules

The public `experiment.py` file re-exports high-level functions and types. Implementation details
live in `src/agent_runtime_python/experiments/`:

- `planning.py` builds trial plans from sweeps or Optuna-style planners.
- `trial_commands.py` builds protocol-compliant worker commands.
- `targets.py` adapts direct workers, internal HTTP streaming, and TypeScript gateway targets.
- `results.py` turns worker events into JSONL trial records.
- `runner.py` coordinates trial execution and telemetry.
- `cli.py` owns command-line parsing.

## Observability Modules

Telemetry is a package under `observability/telemetry/`:

- `spans.py` owns span lifecycle helpers through `AgentRunTelemetry`.
- `attributes.py` maps runtime concepts and provider usage to OpenTelemetry attributes.
- `config.py` configures OTLP export from environment variables.
- `context.py` stores per-run telemetry context.

Structured logs live in `observability/logger.py`, and provider usage aggregation lives in
`observability/usage.py`.

## Operations And Tests

Grafana dashboard generation lives in `ops/observability/dashboards/`, split into builder, query,
and tuning modules. Local observability smoke tests live in `ops/observability/acceptance/`.

Tests are grouped by behavior area: experiment planning/results/targets, worker runtime behavior,
worker telemetry, internal API behavior, and observability dashboard/acceptance helpers.
