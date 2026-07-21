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
