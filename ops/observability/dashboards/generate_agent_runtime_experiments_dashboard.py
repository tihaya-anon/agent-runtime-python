"""Generate the Agent Runtime Experiments Grafana dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from grafana_foundation_sdk.builders.bargauge import Panel as BarGaugePanel
from grafana_foundation_sdk.builders.dashboard import Dashboard, TextBoxVariable
from grafana_foundation_sdk.builders.gauge import Panel as GaugePanel
from grafana_foundation_sdk.builders.heatmap import Panel as HeatmapPanel
from grafana_foundation_sdk.builders.piechart import Panel as PieChartPanel
from grafana_foundation_sdk.builders.prometheus import Dataquery as PrometheusQuery
from grafana_foundation_sdk.builders.stat import Panel as StatPanel
from grafana_foundation_sdk.builders.table import Panel as TablePanel
from grafana_foundation_sdk.builders.tempo import TempoQuery
from grafana_foundation_sdk.builders.timeseries import Panel as TimeseriesPanel
from grafana_foundation_sdk.cog.encoder import JSONEncoder
from grafana_foundation_sdk.models.dashboard import DataSourceRef, GridPos

from agent_runtime_python.observability.telemetry import (
    AGENT_RUN_ID_ATTRIBUTE,
    AGENT_RUN_OUTCOME_ATTRIBUTE,
    EXPERIMENT_OUTCOME_ATTRIBUTE,
    EXPERIMENT_STUDY_ID_ATTRIBUTE,
    EXPERIMENT_TARGET_ATTRIBUTE,
    EXPERIMENT_TRIAL_ID_ATTRIBUTE,
)

DASHBOARD_PATH = Path(__file__).with_name("agent-runtime-experiments.dashboard.json")

PROMETHEUS = DataSourceRef(type_val="prometheus", uid="prometheus")
TEMPO = DataSourceRef(type_val="tempo", uid="tempo")

SERVICE_NAME = "agent-runtime-python"
STUDY_ID_VARIABLE = "study_id"
TRIAL_ID_VARIABLE = "trial_id"
AGENT_RUN_ID_VARIABLE = "agent_run_id"
AGENT_GRAPH_NODE_SPAN = "agent.graph.node"
AGENT_GRAPH_SPAN = "agent.graph"
AGENT_RUN_SPAN = "agent.run"
EXPERIMENT_TRIAL_SPAN = "experiment.trial"
SPANMETRICS_CALLS_TOTAL = "traces_spanmetrics_calls_total"
SPANMETRICS_LATENCY_BUCKET = "traces_spanmetrics_latency_bucket"
SPANMETRICS_WINDOW = "5m"
GRAFANA_FIELD_VALUE = "${__value.raw}"
GRAFANA_TRACE_ID_FIELD = "${__data.fields.traceIdHidden}"
GRAFANA_TIME_RANGE = {"from": "${__from}", "to": "${__to}"}


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
            "High-level experiment health, throughput, latency, and activity "
            "with trace drilldown entry points."
        )
        .tags(["agent-runtime-python", "experiments", "langgraph"])
        .timezone("browser")
        .time("now-6h", "now")
        .refresh("30s")
        .with_variable(text_variable(STUDY_ID_VARIABLE, "Study ID"))
        .with_variable(text_variable(TRIAL_ID_VARIABLE, "Trial ID"))
        .with_variable(text_variable(AGENT_RUN_ID_VARIABLE, "Agent Run ID"))
        .with_panel(
            stat_panel(
                1,
                "Trials / min",
                GridPos(h=4, w=6, x=0, y=0),
                prometheus_query("A", trial_starts_per_min_promql(), "trials/min"),
            )
        )
        .with_panel(
            stat_panel(
                2,
                "Failed Runs / min",
                GridPos(h=4, w=6, x=6, y=0),
                prometheus_query("A", failed_runs_per_min_promql(), "failed/min"),
            )
        )
        .with_panel(
            stat_panel(
                3,
                "Agent Run p95",
                GridPos(h=4, w=6, x=12, y=0),
                prometheus_query("A", agent_run_duration_p95_promql(), "p95"),
            )
        )
        .with_panel(
            gauge_panel(
                4,
                "Trial Error %",
                GridPos(h=4, w=6, x=18, y=0),
                prometheus_query("A", trial_error_ratio_promql(), "error %"),
            )
        )
        .with_panel(
            pie_chart_panel(
                5,
                "Trial Outcome Mix",
                GridPos(h=8, w=8, x=0, y=4),
                prometheus_query("A", trial_outcome_mix_promql(), "{{outcome}}"),
            )
        )
        .with_panel(
            bar_gauge_panel(
                6,
                "Runtime Activity Mix",
                GridPos(h=8, w=8, x=8, y=4),
                prometheus_query("A", runtime_activity_mix_promql(), "{{span_name}}"),
            )
        )
        .with_panel(
            heatmap_panel(
                7,
                "Agent Run Latency Distribution",
                GridPos(h=8, w=8, x=16, y=4),
                prometheus_query(
                    "A", agent_run_latency_distribution_promql(), "{{le}}"
                ),
            )
        )
        .with_panel(
            timeseries_panel(
                8,
                "Trial Starts / min",
                GridPos(h=8, w=12, x=0, y=12),
                prometheus_query("A", trial_rate_promql(), "{{outcome}}"),
            )
        )
        .with_panel(
            timeseries_panel(
                9,
                "Duration p95",
                GridPos(h=8, w=12, x=12, y=12),
                prometheus_query("A", duration_p95_by_span_promql(), "{{span_name}}"),
            )
        )
        .with_panel(
            table_panel(
                10,
                "Recent Trial Drilldown",
                GridPos(h=8, w=24, x=0, y=20),
                tempo_query("A", recent_trials_traceql(), 50),
            )
        )
        .build()
    )
    return tune_panels(add_tempo_table_types(to_json_dict(dashboard)))


def text_variable(name: str, label: str) -> TextBoxVariable:
    return TextBoxVariable(name).label(label)


def table_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: TempoQuery,
) -> TablePanel:
    return (
        TablePanel()
        .id(panel_id)
        .title(title)
        .grid_pos(grid_pos)
        .datasource(TEMPO)
        .with_target(query)
    )


def stat_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> StatPanel:
    return (
        StatPanel()
        .id(panel_id)
        .title(title)
        .grid_pos(grid_pos)
        .datasource(PROMETHEUS)
        .with_target(query)
    )


def gauge_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> GaugePanel:
    return (
        GaugePanel()
        .id(panel_id)
        .title(title)
        .grid_pos(grid_pos)
        .datasource(PROMETHEUS)
        .with_target(query)
    )


def pie_chart_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> PieChartPanel:
    return (
        PieChartPanel()
        .id(panel_id)
        .title(title)
        .grid_pos(grid_pos)
        .datasource(PROMETHEUS)
        .with_target(query.instant())
    )


def bar_gauge_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> BarGaugePanel:
    return (
        BarGaugePanel()
        .id(panel_id)
        .title(title)
        .grid_pos(grid_pos)
        .datasource(PROMETHEUS)
        .with_target(query.instant())
    )


def heatmap_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> HeatmapPanel:
    return (
        HeatmapPanel()
        .id(panel_id)
        .title(title)
        .grid_pos(grid_pos)
        .datasource(PROMETHEUS)
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


def prometheus_query(ref_id: str, expr: str, legend_format: str) -> PrometheusQuery:
    return (
        PrometheusQuery()
        .ref_id(ref_id)
        .datasource(PROMETHEUS)
        .expr(expr)
        .legend_format(legend_format)
    )


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
        f'&& span:name = "{EXPERIMENT_TRIAL_SPAN}" '
        f"&& {selected_filter(EXPERIMENT_STUDY_ID_ATTRIBUTE, STUDY_ID_VARIABLE)} "
        f"&& {selected_filter(EXPERIMENT_TRIAL_ID_ATTRIBUTE, TRIAL_ID_VARIABLE)} "
        f"&& {selected_filter(AGENT_RUN_ID_ATTRIBUTE, AGENT_RUN_ID_VARIABLE)} "
        f"}} | {fields}"
    )


def trial_rate_promql() -> str:
    return (
        "sum by (outcome) ("
        f"{span_status_outcome_promql(trial_rate_by_status_promql('STATUS_CODE_OK'), 'succeeded')} "
        "or "
        f"{span_status_outcome_promql(trial_rate_by_status_promql('STATUS_CODE_ERROR'), 'failed')}"
        ")"
    )


def trial_starts_per_min_promql() -> str:
    return (
        f"sum(rate({SPANMETRICS_CALLS_TOTAL}"
        f'{{service="{SERVICE_NAME}",span_name="{EXPERIMENT_TRIAL_SPAN}"}}'
        f"[{SPANMETRICS_WINDOW}]) * 60)"
    )


def failed_runs_per_min_promql() -> str:
    return (
        f"sum(rate({SPANMETRICS_CALLS_TOTAL}"
        f'{{service="{SERVICE_NAME}",span_name="{AGENT_RUN_SPAN}",'
        'status_code="STATUS_CODE_ERROR"}'
        f"[{SPANMETRICS_WINDOW}]) * 60)"
    )


def trial_error_ratio_promql() -> str:
    errored = (
        f"sum(rate({SPANMETRICS_CALLS_TOTAL}"
        f'{{service="{SERVICE_NAME}",span_name="{EXPERIMENT_TRIAL_SPAN}",'
        'status_code="STATUS_CODE_ERROR"}'
        f"[{SPANMETRICS_WINDOW}]))"
    )
    total = (
        f"sum(rate({SPANMETRICS_CALLS_TOTAL}"
        f'{{service="{SERVICE_NAME}",span_name="{EXPERIMENT_TRIAL_SPAN}"}}'
        f"[{SPANMETRICS_WINDOW}]))"
    )
    return f"100 * {errored} / clamp_min({total}, 0.001)"


def trial_outcome_mix_promql() -> str:
    return (
        "sum by (outcome) ("
        f"{span_status_outcome_promql(trial_increase_by_status_promql('STATUS_CODE_OK'), 'succeeded')} "
        "or "
        f"{span_status_outcome_promql(trial_increase_by_status_promql('STATUS_CODE_ERROR'), 'failed')}"
        ")"
    )


def runtime_activity_mix_promql() -> str:
    return (
        "sum by (span_name) "
        f"(increase({SPANMETRICS_CALLS_TOTAL}"
        f'{{service="{SERVICE_NAME}",span_name=~"'
        f"{EXPERIMENT_TRIAL_SPAN}|{AGENT_RUN_SPAN}|"
        f"{AGENT_GRAPH_SPAN}|{AGENT_GRAPH_NODE_SPAN}"
        '"}[$__range]))'
    )


def agent_run_duration_p95_promql() -> str:
    return (
        "histogram_quantile(0.95, sum by (le, span_name) "
        f"(rate({SPANMETRICS_LATENCY_BUCKET}"
        f'{{service="{SERVICE_NAME}",span_name="{AGENT_RUN_SPAN}"}}'
        f"[{SPANMETRICS_WINDOW}])))"
    )


def duration_p95_by_span_promql() -> str:
    return (
        "histogram_quantile(0.95, sum by (le, span_name) "
        f"(rate({SPANMETRICS_LATENCY_BUCKET}"
        f'{{service="{SERVICE_NAME}",span_name=~"'
        f"{EXPERIMENT_TRIAL_SPAN}|{AGENT_RUN_SPAN}|"
        f"{AGENT_GRAPH_SPAN}|{AGENT_GRAPH_NODE_SPAN}"
        f'"}}[{SPANMETRICS_WINDOW}])))'
    )


def agent_run_latency_distribution_promql() -> str:
    return (
        "sum by (le) "
        f"(rate({SPANMETRICS_LATENCY_BUCKET}"
        f'{{service="{SERVICE_NAME}",span_name="{AGENT_RUN_SPAN}"}}'
        f"[{SPANMETRICS_WINDOW}]))"
    )


def trial_rate_by_status_promql(status_code: str) -> str:
    return (
        f"rate({SPANMETRICS_CALLS_TOTAL}"
        f'{{service="{SERVICE_NAME}",span_name="{EXPERIMENT_TRIAL_SPAN}",'
        f'status_code="{status_code}"}}'
        f"[{SPANMETRICS_WINDOW}]) * 60"
    )


def trial_increase_by_status_promql(status_code: str) -> str:
    return (
        f"increase({SPANMETRICS_CALLS_TOTAL}"
        f'{{service="{SERVICE_NAME}",span_name="{EXPERIMENT_TRIAL_SPAN}",'
        f'status_code="{status_code}"}}'
        "[$__range])"
    )


def span_status_outcome_promql(expr: str, outcome: str) -> str:
    return f'label_replace({expr}, "outcome", "{outcome}", "status_code", ".*")'


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


def tune_panels(dashboard: dict[str, Any]) -> dict[str, Any]:
    for panel in dashboard.get("panels", []):
        if not isinstance(panel, dict):
            continue

        panel_id = panel.get("id")
        panel_type = panel.get("type")
        field_defaults = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
        targets = [
            target for target in panel.get("targets", []) if isinstance(target, dict)
        ]

        if panel_type == "stat":
            panel["options"] = {
                "colorMode": "background",
                "graphMode": "area",
                "justifyMode": "center",
                "orientation": "auto",
                "reduceOptions": last_not_null_reduce_options(),
                "textMode": "auto",
                "wideLayout": True,
            }
            field_defaults["decimals"] = 2
            field_defaults["noValue"] = "0"
            if panel_id == 3:
                field_defaults["unit"] = "s"

        if panel_type == "gauge":
            panel["options"] = {
                "orientation": "auto",
                "reduceOptions": last_not_null_reduce_options(),
                "showThresholdLabels": False,
                "showThresholdMarkers": True,
            }
            field_defaults["decimals"] = 1
            field_defaults["max"] = 100
            field_defaults["min"] = 0
            field_defaults["noValue"] = "0"
            field_defaults["unit"] = "percent"
            field_defaults["thresholds"] = {
                "mode": "absolute",
                "steps": [
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 5},
                    {"color": "red", "value": 20},
                ],
            }

        if panel_type == "piechart":
            panel["options"] = {
                "displayLabels": ["name", "percent"],
                "legend": {
                    "displayMode": "table",
                    "placement": "right",
                    "showLegend": True,
                    "values": ["value", "percent"],
                },
                "pieType": "donut",
                "reduceOptions": last_not_null_reduce_options(),
                "tooltip": {"mode": "multi", "sort": "none"},
            }
            field_defaults["decimals"] = 0
            field_defaults["noValue"] = "0"

        if panel_type == "bargauge":
            panel["options"] = {
                "displayMode": "gradient",
                "orientation": "horizontal",
                "reduceOptions": last_not_null_reduce_options(),
                "showUnfilled": True,
                "valueMode": "color",
            }
            field_defaults["decimals"] = 0
            field_defaults["noValue"] = "0"

        if panel_type == "heatmap":
            for target in targets:
                target["format"] = "heatmap"
            panel["options"] = {
                "calculate": False,
                "cellGap": 1,
                "color": {
                    "mode": "scheme",
                    "scheme": "Spectral",
                    "steps": 64,
                },
                "legend": {"show": True},
                "tooltip": {"show": True},
                "yAxis": {"axisPlacement": "left", "unit": "s"},
            }
            field_defaults["unit"] = "s"

        if panel_type == "timeseries":
            panel["options"] = {
                "legend": {
                    "displayMode": "table",
                    "placement": "bottom",
                    "showLegend": True,
                },
                "tooltip": {"mode": "multi", "sort": "desc"},
            }
            field_defaults["decimals"] = 2
            if panel_id == 9:
                field_defaults["unit"] = "s"

        if panel_type == "table":
            panel["description"] = (
                "Use trace and span links as the drilldown path into Tempo; "
                "filter logs in Grafana Explore by agent_run_id when needed."
            )
            panel["options"] = {
                "cellHeight": "sm",
                "footer": {"show": False},
                "showHeader": True,
            }
            field_defaults["custom"] = {"align": "auto", "inspect": False}
            panel.setdefault("fieldConfig", {}).setdefault("overrides", []).extend(
                [
                    field_link_override(
                        "traceID",
                        {"traceId": GRAFANA_FIELD_VALUE},
                    ),
                    field_link_override(
                        "spanID",
                        {
                            "traceId": GRAFANA_TRACE_ID_FIELD,
                            "spanId": GRAFANA_FIELD_VALUE,
                        },
                    ),
                ]
            )

        if panel_type != "heatmap":
            for target in targets:
                target.pop("format", None)

    return dashboard


def last_not_null_reduce_options() -> dict[str, Any]:
    return {"calcs": ["lastNotNull"], "fields": "", "values": False}


def field_link_override(
    field_name: str,
    trace_link: dict[str, str],
) -> dict[str, Any]:
    return {
        "matcher": {"id": "byName", "options": field_name},
        "properties": [
            {"id": "links", "value": None},
            {"id": "custom.cellOptions", "value": {"type": "data-links"}},
            {
                "id": "links",
                "value": [
                    {
                        "title": f"{GRAFANA_FIELD_VALUE} ↗",
                        "url": trace_explore_url(trace_link),
                        "targetBlank": True,
                    }
                ],
            },
        ],
    }


def trace_explore_url(trace_link: dict[str, str]) -> str:
    pane: dict[str, Any] = {
        "datasource": TEMPO.uid,
        "queries": [
            {
                "query": trace_link["traceId"],
                "queryType": "traceql",
                "datasource": {"type": TEMPO.type_val, "uid": TEMPO.uid},
                "refId": "A",
                "limit": 20,
                "tableType": "traces",
                "metricsQueryType": "range",
            }
        ],
        "range": GRAFANA_TIME_RANGE,
        "compact": False,
    }
    span_id = trace_link.get("spanId")
    if span_id is not None:
        pane["panelsState"] = {"trace": {"spanId": span_id}}

    encoded_panes = quote(json.dumps({"agentRunTrace": pane}, separators=(",", ":")))
    for variable in [
        GRAFANA_FIELD_VALUE,
        GRAFANA_TRACE_ID_FIELD,
        *GRAFANA_TIME_RANGE.values(),
    ]:
        encoded_panes = encoded_panes.replace(quote(variable), variable)

    return f"/explore?schemaVersion=1&panes={encoded_panes}"


if __name__ == "__main__":
    raise SystemExit(main())
