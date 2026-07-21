"""Generate the Agent Runtime Experiments Grafana dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from grafana_foundation_sdk.builders.dashboard import Dashboard, TextBoxVariable
from grafana_foundation_sdk.builders.loki import Dataquery as LokiQuery
from grafana_foundation_sdk.builders.prometheus import Dataquery as PrometheusQuery
from grafana_foundation_sdk.builders.table import Panel as TablePanel
from grafana_foundation_sdk.builders.tempo import TempoQuery
from grafana_foundation_sdk.builders.timeseries import Panel as TimeseriesPanel
from grafana_foundation_sdk.cog.encoder import JSONEncoder
from grafana_foundation_sdk.models.dashboard import DataSourceRef, GridPos
from openinference.semconv.trace import SpanAttributes

from agent_runtime_python.observability.telemetry import (
    AGENT_RUN_ERROR_CLASSIFICATION_ATTRIBUTE,
    AGENT_RUN_ID_ATTRIBUTE,
    AGENT_RUN_OUTCOME_ATTRIBUTE,
    EXPERIMENT_OUTCOME_ATTRIBUTE,
    EXPERIMENT_STUDY_ID_ATTRIBUTE,
    EXPERIMENT_TARGET_ATTRIBUTE,
    EXPERIMENT_TRIAL_ID_ATTRIBUTE,
    GRAPH_ID_ATTRIBUTE,
    GRAPH_NODE_NAME_ATTRIBUTE,
    RUNTIME_PROFILE_ID_ATTRIBUTE,
)

DASHBOARD_PATH = Path(__file__).with_name("agent-runtime-experiments.dashboard.json")

PROMETHEUS = DataSourceRef(type_val="prometheus", uid="prometheus")
TEMPO = DataSourceRef(type_val="tempo", uid="tempo")
LOKI = DataSourceRef(type_val="loki", uid="loki")

SERVICE_NAME = "agent-runtime-python"
STUDY_ID_VARIABLE = "study_id"
TRIAL_ID_VARIABLE = "trial_id"
GRAPH_ID_VARIABLE = "graph_id"
AGENT_RUN_ID_VARIABLE = "agent_run_id"


def main() -> int:
    dashboard = build_dashboard()
    DASHBOARD_PATH.write_text(
        f"{json.dumps(dashboard, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return 0


def build_dashboard() -> dict[str, Any]:
    dashboard = (
        Dashboard("Agent Runtime Experiments")
        .uid("agent-runtime-experiments")
        .description(
            "Inspect provider-owned Python runtime studies, trials, graphs, nodes, "
            "outcomes, and correlated logs."
        )
        .tags(["agent-runtime-python", "experiments", "langgraph"])
        .timezone("browser")
        .time("now-6h", "now")
        .refresh("30s")
        .with_variable(text_variable(STUDY_ID_VARIABLE, "Study ID"))
        .with_variable(text_variable(TRIAL_ID_VARIABLE, "Trial ID"))
        .with_variable(text_variable(GRAPH_ID_VARIABLE, "Graph ID"))
        .with_variable(text_variable(AGENT_RUN_ID_VARIABLE, "Agent Run ID"))
        .with_panel(
            table_panel(
                1,
                "Recent Experiment Trials",
                GridPos(h=9, w=24, x=0, y=0),
                tempo_query("A", recent_trials_traceql(), 200),
            )
        )
        .with_panel(
            timeseries_panel(
                2,
                "Trial Starts by Outcome",
                GridPos(h=8, w=12, x=0, y=9),
                prometheus_query("A", trial_rate_promql()),
            )
        )
        .with_panel(
            timeseries_panel(
                3,
                "Agent Run Duration p95",
                GridPos(h=8, w=12, x=12, y=9),
                prometheus_query("A", agent_run_duration_p95_promql()),
            )
        )
        .with_panel(
            table_panel(
                4,
                "Selected Trial Trace",
                GridPos(h=10, w=24, x=0, y=17),
                tempo_query("A", selected_trial_traceql(), 200),
            )
        )
        .with_panel(
            table_panel(
                5,
                "Graph and Node Breakdown",
                GridPos(h=10, w=24, x=0, y=27),
                tempo_query("A", graph_node_traceql(), 200),
            )
        )
        .with_panel(
            table_panel(
                6,
                "Failed Runtime Runs",
                GridPos(h=8, w=24, x=0, y=37),
                tempo_query("A", failed_runs_traceql(), 100),
            )
        )
        .with_panel(
            table_panel(
                7,
                "Correlated Runtime Logs",
                GridPos(h=10, w=24, x=0, y=45),
                loki_query("A", correlated_logs_logql()),
            )
        )
        .build()
    )
    return add_tempo_table_types(to_json_dict(dashboard))


def text_variable(name: str, label: str) -> TextBoxVariable:
    return TextBoxVariable(name).label(label)


def table_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: TempoQuery | LokiQuery,
) -> TablePanel:
    return (
        TablePanel()
        .id(panel_id)
        .title(title)
        .grid_pos(grid_pos)
        .datasource(query_datasource(query))
        .with_target(query)
    )


def timeseries_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> TimeseriesPanel:
    return (
        TimeseriesPanel()
        .id(panel_id)
        .title(title)
        .grid_pos(grid_pos)
        .datasource(PROMETHEUS)
        .with_target(query)
    )


def tempo_query(
    ref_id: str,
    query: str,
    limit: int,
) -> TempoQuery:
    return (
        TempoQuery()
        .ref_id(ref_id)
        .datasource(TEMPO)
        .query_type("traceql")
        .query(query)
        .limit(limit)
    )


def prometheus_query(ref_id: str, expr: str) -> PrometheusQuery:
    return (
        PrometheusQuery()
        .ref_id(ref_id)
        .datasource(PROMETHEUS)
        .expr(expr)
        .legend_format("{{span_name}} {{status_code}}")
    )


def loki_query(ref_id: str, expr: str) -> LokiQuery:
    return LokiQuery().ref_id(ref_id).datasource(LOKI).expr(expr).query_type("range")


def query_datasource(query: TempoQuery | LokiQuery) -> DataSourceRef:
    if isinstance(query, TempoQuery):
        return TEMPO
    return LOKI


def span_attribute(name: str) -> str:
    return f'span."{name}"'


def selected_filter(attribute_name: str, variable_name: str) -> str:
    template = f"${variable_name}"
    return (
        "true"
        if template == ""
        else f'({span_attribute(attribute_name)} = "{template}" || "{template}" = "")'
    )


def recent_trials_traceql() -> str:
    fields = select_fields(
        [
            "span:name",
            "trace:id",
            "span:duration",
            "span:status",
            span_attribute(EXPERIMENT_STUDY_ID_ATTRIBUTE),
            span_attribute(EXPERIMENT_TRIAL_ID_ATTRIBUTE),
            span_attribute(EXPERIMENT_TARGET_ATTRIBUTE),
            span_attribute(EXPERIMENT_OUTCOME_ATTRIBUTE),
            span_attribute(AGENT_RUN_ID_ATTRIBUTE),
            span_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE),
        ]
    )
    return (
        f'{{ resource.service.name = "{SERVICE_NAME}" '
        f'&& span:name = "experiment.trial" '
        f"&& {selected_filter(EXPERIMENT_STUDY_ID_ATTRIBUTE, STUDY_ID_VARIABLE)} "
        f"}} | {fields}"
    )


def selected_trial_traceql() -> str:
    fields = select_fields(
        [
            "span:name",
            "trace:id",
            "span:duration",
            "span:status",
            span_attribute(EXPERIMENT_STUDY_ID_ATTRIBUTE),
            span_attribute(EXPERIMENT_TRIAL_ID_ATTRIBUTE),
            span_attribute(AGENT_RUN_ID_ATTRIBUTE),
            span_attribute(RUNTIME_PROFILE_ID_ATTRIBUTE),
            span_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE),
            span_attribute(AGENT_RUN_ERROR_CLASSIFICATION_ATTRIBUTE),
        ]
    )
    return (
        f'{{ resource.service.name = "{SERVICE_NAME}" '
        f'&& {span_attribute(EXPERIMENT_STUDY_ID_ATTRIBUTE)} = "${STUDY_ID_VARIABLE}" '
        f'&& {span_attribute(EXPERIMENT_TRIAL_ID_ATTRIBUTE)} = "${TRIAL_ID_VARIABLE}" '
        f"}} &>> {{ true }} | {fields}"
    )


def graph_node_traceql() -> str:
    fields = select_fields(
        [
            "span:name",
            "trace:id",
            "span:duration",
            "span:status",
            span_attribute(GRAPH_ID_ATTRIBUTE),
            span_attribute(GRAPH_NODE_NAME_ATTRIBUTE),
            span_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND),
            span_attribute(SpanAttributes.LLM_MODEL_NAME),
            span_attribute(SpanAttributes.TOOL_NAME),
        ]
    )
    return (
        f'{{ resource.service.name = "{SERVICE_NAME}" '
        f"&& {selected_filter(GRAPH_ID_ATTRIBUTE, GRAPH_ID_VARIABLE)} "
        f'&& (span:name = "agent.graph" || span:name = "agent.graph.node") '
        f"}} | {fields}"
    )


def failed_runs_traceql() -> str:
    fields = select_fields(
        [
            "span:name",
            "trace:id",
            "span:duration",
            "span:status",
            span_attribute(AGENT_RUN_ID_ATTRIBUTE),
            span_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE),
            span_attribute(AGENT_RUN_ERROR_CLASSIFICATION_ATTRIBUTE),
            span_attribute(RUNTIME_PROFILE_ID_ATTRIBUTE),
            span_attribute(GRAPH_ID_ATTRIBUTE),
        ]
    )
    return (
        f'{{ resource.service.name = "{SERVICE_NAME}" '
        f'&& span:name = "agent.run" '
        f'&& {span_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE)} = "failed" '
        f"&& {selected_filter(AGENT_RUN_ID_ATTRIBUTE, AGENT_RUN_ID_VARIABLE)} "
        f"}} | {fields}"
    )


def correlated_logs_logql() -> str:
    return (
        f'{{service_name="{SERVICE_NAME}"}} | json | __error__="" '
        f'| agent_run_id="${AGENT_RUN_ID_VARIABLE}"'
    )


def trial_rate_promql() -> str:
    return (
        "sum by (span_name, status_code) "
        "(rate(traces_spanmetrics_calls_total"
        f'{{service="{SERVICE_NAME}",span_name="experiment.trial"}}[5m]))'
    )


def agent_run_duration_p95_promql() -> str:
    return (
        "histogram_quantile(0.95, sum by (le, span_name) "
        "(rate(traces_spanmetrics_latency_bucket"
        f'{{service="{SERVICE_NAME}",span_name="agent.run"}}[5m])))'
    )


def select_fields(fields: list[str]) -> str:
    return f"select({', '.join(fields)})"


def to_json_dict(value: Any) -> dict[str, Any]:
    encoded = json.loads(json.dumps(value, cls=JSONEncoder))
    if not isinstance(encoded, dict):
        raise TypeError("Dashboard generator must produce a JSON object")

    return encoded


def add_tempo_table_types(dashboard: dict[str, Any]) -> dict[str, Any]:
    for panel in dashboard.get("panels", []):
        if not isinstance(panel, dict):
            continue

        for target in panel.get("targets", []):
            if not isinstance(target, dict):
                continue
            datasource = target.get("datasource")
            if isinstance(datasource, dict) and datasource.get("uid") == TEMPO.uid:
                target["tableType"] = "spans"

    return dashboard


if __name__ == "__main__":
    raise SystemExit(main())
