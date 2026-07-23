"""Build the Agent Runtime Experiments dashboard model."""

from __future__ import annotations

import json
from typing import Any

from grafana_foundation_sdk.builders.barchart import Panel as BarChartPanel
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

from dashboard_queries import (
    AGENT_RUN_ID_VARIABLE,
    STUDY_ID_VARIABLE,
    TRIAL_ID_VARIABLE,
    TRIAL_OUTCOME_VARIABLE,
    agent_run_duration_p95_promql,
    agent_run_latency_distribution_promql,
    duration_p95_by_span_promql,
    failed_runs_per_min_promql,
    model_call_latency_p95_promql,
    provider_cache_tokens_traceql,
    provider_usage_by_graph_node_traceql,
    provider_usage_by_study_model_traceql,
    recent_trial_usage_traceql,
    runtime_activity_mix_promql,
    trial_error_ratio_promql,
    trial_outcome_mix_promql,
    trial_rate_promql,
    trial_starts_per_min_promql,
)
from dashboard_tuning import add_tempo_table_types, tune_panels

PROMETHEUS = DataSourceRef(type_val="prometheus", uid="prometheus")
TEMPO = DataSourceRef(type_val="tempo", uid="tempo")


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
        .with_variable(text_variable(TRIAL_OUTCOME_VARIABLE, "Trial Outcome"))
        .with_variable(text_variable(AGENT_RUN_ID_VARIABLE, "Agent Run ID"))
        .with_panel(stat_card(1, "Trials / min", 0, trial_starts_per_min_promql()))
        .with_panel(stat_card(2, "Failed Runs / min", 6, failed_runs_per_min_promql()))
        .with_panel(stat_card(3, "Agent Run p95", 12, agent_run_duration_p95_promql()))
        .with_panel(gauge_card(4, "Trial Error %", 18, trial_error_ratio_promql()))
        .with_panel(mix_panel(5, "Trial Outcome Mix", 0, trial_outcome_mix_promql()))
        .with_panel(activity_panel())
        .with_panel(latency_heatmap_panel())
        .with_panel(rate_timeseries_panel())
        .with_panel(duration_timeseries_panel())
        .with_panel(usage_by_study_model_panel())
        .with_panel(usage_by_graph_node_panel())
        .with_panel(provider_cache_tokens_panel())
        .with_panel(model_call_latency_panel())
        .with_panel(drilldown_table_panel())
        .build()
    )
    return tune_panels(add_tempo_table_types(to_json_dict(dashboard)))


def text_variable(name: str, label: str) -> TextBoxVariable:
    return TextBoxVariable(name).label(label)


def stat_card(panel_id: int, title: str, x: int, expr: str) -> StatPanel:
    return stat_panel(
        panel_id,
        title,
        GridPos(h=4, w=6, x=x, y=0),
        prometheus_query("A", expr, _legend_for_stat(title)),
    )


def gauge_card(panel_id: int, title: str, x: int, expr: str) -> GaugePanel:
    return gauge_panel(
        panel_id,
        title,
        GridPos(h=4, w=6, x=x, y=0),
        prometheus_query("A", expr, "error %"),
    )


def mix_panel(panel_id: int, title: str, x: int, expr: str) -> PieChartPanel:
    return pie_chart_panel(
        panel_id,
        title,
        GridPos(h=8, w=8, x=x, y=4),
        prometheus_query("A", expr, "{{outcome}}"),
    )


def activity_panel() -> BarGaugePanel:
    return bar_gauge_panel(
        6,
        "Runtime Activity Mix",
        GridPos(h=8, w=8, x=8, y=4),
        prometheus_query("A", runtime_activity_mix_promql(), "{{span_name}}"),
    )


def latency_heatmap_panel() -> HeatmapPanel:
    return heatmap_panel(
        7,
        "Agent Run Latency Distribution",
        GridPos(h=8, w=8, x=16, y=4),
        prometheus_query("A", agent_run_latency_distribution_promql(), "{{le}}"),
    )


def rate_timeseries_panel() -> TimeseriesPanel:
    return timeseries_panel(
        8,
        "Trial Starts / min",
        GridPos(h=8, w=12, x=0, y=12),
        prometheus_query("A", trial_rate_promql(), "{{outcome}}"),
    )


def duration_timeseries_panel() -> TimeseriesPanel:
    return timeseries_panel(
        9,
        "Duration p95",
        GridPos(h=8, w=12, x=12, y=12),
        prometheus_query("A", duration_p95_by_span_promql(), "{{span_name}}"),
    )


def drilldown_table_panel() -> TablePanel:
    return table_panel(
        10,
        "Recent Trial Drilldown",
        GridPos(h=8, w=24, x=0, y=36),
        tempo_query("A", recent_trial_usage_traceql(), 50),
    )


def usage_by_study_model_panel() -> BarChartPanel:
    return bar_chart_tempo_panel(
        11,
        "Provider Tokens by Model",
        GridPos(h=8, w=12, x=0, y=20),
        tempo_query("A", provider_usage_by_study_model_traceql(), 100),
    )


def usage_by_graph_node_panel() -> BarChartPanel:
    return bar_chart_tempo_panel(
        12,
        "Provider Tokens by Graph Node",
        GridPos(h=8, w=12, x=12, y=20),
        tempo_query("A", provider_usage_by_graph_node_traceql(), 100),
    )


def provider_cache_tokens_panel() -> BarChartPanel:
    return bar_chart_tempo_panel(
        13,
        "Provider Cache Tokens",
        GridPos(h=8, w=12, x=0, y=28),
        tempo_query("A", provider_cache_tokens_traceql(), 100),
    )


def model_call_latency_panel() -> StatPanel:
    return stat_panel(
        14,
        "Model Call Latency p95",
        GridPos(h=8, w=12, x=12, y=28),
        prometheus_query("A", model_call_latency_p95_promql(), "p95"),
    )


def table_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: TempoQuery,
) -> TablePanel:
    return _panel(TablePanel(), panel_id, title, grid_pos, TEMPO).with_target(query)


def stat_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> StatPanel:
    return _panel(StatPanel(), panel_id, title, grid_pos, PROMETHEUS).with_target(query)


def gauge_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> GaugePanel:
    return _panel(GaugePanel(), panel_id, title, grid_pos, PROMETHEUS).with_target(
        query
    )


def pie_chart_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> PieChartPanel:
    return _panel(PieChartPanel(), panel_id, title, grid_pos, PROMETHEUS).with_target(
        query.instant()
    )


def bar_gauge_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> BarGaugePanel:
    return _panel(BarGaugePanel(), panel_id, title, grid_pos, PROMETHEUS).with_target(
        query.instant()
    )


def bar_chart_tempo_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: TempoQuery,
) -> BarChartPanel:
    return _panel(BarChartPanel(), panel_id, title, grid_pos, TEMPO).with_target(query)


def heatmap_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> HeatmapPanel:
    return _panel(HeatmapPanel(), panel_id, title, grid_pos, PROMETHEUS).with_target(
        query
    )


def timeseries_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    query: PrometheusQuery,
) -> TimeseriesPanel:
    return _panel(TimeseriesPanel(), panel_id, title, grid_pos, PROMETHEUS).with_target(
        query
    )


def timeseries_tempo_panel(
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    *queries: TempoQuery,
) -> TimeseriesPanel:
    panel = _panel(TimeseriesPanel(), panel_id, title, grid_pos, TEMPO)
    for query in queries:
        panel = panel.with_target(query)

    return panel


def tempo_query(ref_id: str, query: str, limit: int) -> TempoQuery:
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


def to_json_dict(value: Any) -> dict[str, Any]:
    encoded = json.loads(json.dumps(value, cls=JSONEncoder))
    if not isinstance(encoded, dict):
        raise TypeError("Dashboard generator must produce a JSON object")

    return encoded


def _panel(
    panel: Any,
    panel_id: int,
    title: str,
    grid_pos: GridPos,
    datasource: DataSourceRef,
) -> Any:
    return panel.id(panel_id).title(title).grid_pos(grid_pos).datasource(datasource)


def _legend_for_stat(title: str) -> str:
    return {
        "Trials / min": "trials/min",
        "Failed Runs / min": "failed/min",
        "Agent Run p95": "p95",
    }[title]
