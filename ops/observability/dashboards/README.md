# Agent Runtime Grafana Dashboards

This directory is the Git provisioning source for Python runtime dashboards.

## Agent Runtime Experiments

- Generated artifact: `agent-runtime-experiments.dashboard.json`
- Authoring source: `generate_agent_runtime_experiments_dashboard.py`

Regenerate after intentional dashboard changes:

```bash
uv run python ops/observability/dashboards/generate_agent_runtime_experiments_dashboard.py
```

Configure Grafana Git provisioning in the PGL stack to load `*.dashboard.json` files from this
directory. The production Agent Run diagnosis dashboard remains in `agent-workbench`; this dashboard
is detailed experiment/runtime observability for `agent-runtime-python`.

## PGL Smoke Check

After PGL has synced this repository from GitHub, verify that Grafana loaded the dashboard and kept
the expected PGL datasource references:

```bash
uv run python ops/observability/acceptance/smoke_dashboard.py
```

The script defaults to `http://127.0.0.1:3000` with `admin:admin`, checks Grafana health, validates
the `prometheus`, `tempo`, and `loki` datasource UIDs, and compares the loaded dashboard contract
against `agent-runtime-experiments.dashboard.json`.

Override local Grafana settings with `GRAFANA_URL`, `GRAFANA_USER`, and `GRAFANA_PASSWORD`. To
assert the dashboard came from a specific GitHub-sync folder, set `GRAFANA_EXPECT_FOLDER_TITLE`.

## Observability Acceptance

To start the Python runtime compose service, produce deterministic internal HTTP Agent Run telemetry,
and verify that PGL receives traces, logs, and span metrics:

```bash
uv run python ops/observability/acceptance/run_observability_smoke.py
```

Start PGL first so Grafana, Tempo, Loki, Prometheus, Alloy, and the external `observability` Docker
network exist. The acceptance runner builds and starts `compose.observability.yaml`, runs a two-trial
successful experiment plus one unsupported-graph failure through `POST /internal/agent-runs`, waits
for telemetry to appear, and prints the `study_id`, `trial_id`, `graph_id`, successful
`agent_run_id`, and `failed_agent_run_id` values to paste into the dashboard variables.

To verify the current Provider Usage stage specifically, run the synthetic usage graph inside the
runtime container and assert that usage appears in both the JSONL trial result and PGL telemetry:

```bash
uv run agent-runtime-python-provider-usage-smoke
```

This writes `/tmp/agent-runtime-python-provider-usage-smoke.jsonl` by default and fails unless the
record includes `usage`/`modelUsage`, Tempo contains the corresponding `agent.run` and
`gen_ai.inference.client` usage attributes, and Prometheus has a model-call latency p95 sample.
