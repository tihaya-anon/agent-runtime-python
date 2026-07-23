"""Grafana JSON tuning that the foundation SDK does not model directly."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from grafana_foundation_sdk.models.dashboard import DataSourceRef

from dashboard_queries import (
    AGENT_RUN_ID_VARIABLE,
    STUDY_ID_VARIABLE,
    TRIAL_ID_VARIABLE,
    TRIAL_OUTCOME_VARIABLE,
)

TEMPO = DataSourceRef(type_val="tempo", uid="tempo")
GRAFANA_FIELD_VALUE = "${__value.raw}"
GRAFANA_TRACE_ID_FIELD = "${__data.fields.traceIdHidden}"
GRAFANA_TIME_RANGE = {"from": "${__from}", "to": "${__to}"}


def add_tempo_table_types(dashboard: dict[str, Any]) -> dict[str, Any]:
    for panel in dashboard.get("panels", []):
        if not isinstance(panel, dict):
            continue

        for target in panel.get("targets", []):
            if not _is_tempo_target(target):
                continue
            if panel.get("type") == "table" or _is_traceql_select_query(target):
                target["tableType"] = "spans"
            if _is_traceql_metrics_query(target):
                target["metricsQueryType"] = "range"

    return dashboard


def tune_panels(dashboard: dict[str, Any]) -> dict[str, Any]:
    for panel in dashboard.get("panels", []):
        if not isinstance(panel, dict):
            continue

        _tune_panel(panel)

    return dashboard


def _tune_panel(panel: dict[str, Any]) -> None:
    panel_type = panel.get("type")
    field_defaults = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
    targets = [
        target for target in panel.get("targets", []) if isinstance(target, dict)
    ]

    if panel_type == "stat":
        _tune_stat_panel(panel, field_defaults)
    if panel_type == "gauge":
        _tune_gauge_panel(panel, field_defaults)
    if panel_type == "piechart":
        _tune_pie_chart_panel(panel, field_defaults)
    if panel_type == "bargauge":
        _tune_bar_gauge_panel(panel, field_defaults)
    if panel_type == "barchart":
        _tune_bar_chart_panel(panel, field_defaults)
    if panel_type == "heatmap":
        _tune_heatmap_panel(panel, field_defaults, targets)
    if panel_type == "timeseries":
        _tune_timeseries_panel(panel, field_defaults, targets)
    if panel_type == "table":
        _tune_table_panel(panel, field_defaults)
    if panel_type != "heatmap":
        for target in targets:
            target.pop("format", None)


def _tune_stat_panel(panel: dict[str, Any], field_defaults: dict[str, Any]) -> None:
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
    if panel.get("id") in {3, 14}:
        field_defaults["unit"] = "s"


def _tune_gauge_panel(panel: dict[str, Any], field_defaults: dict[str, Any]) -> None:
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


def _tune_pie_chart_panel(
    panel: dict[str, Any], field_defaults: dict[str, Any]
) -> None:
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
    if panel.get("id") == 5:
        field_defaults["links"] = [trial_outcome_filter_link()]


def _tune_bar_gauge_panel(
    panel: dict[str, Any], field_defaults: dict[str, Any]
) -> None:
    panel["options"] = {
        "displayMode": "gradient",
        "orientation": "horizontal",
        "reduceOptions": last_not_null_reduce_options(),
        "showUnfilled": True,
        "valueMode": "color",
    }
    field_defaults["decimals"] = 0
    field_defaults["noValue"] = "0"


def _tune_bar_chart_panel(
    panel: dict[str, Any], field_defaults: dict[str, Any]
) -> None:
    x_field = _provider_usage_x_field(panel.get("id"))
    if x_field is None:
        return

    panel["options"] = {
        "barRadius": 0,
        "barWidth": 0.88,
        "fullHighlight": True,
        "groupWidth": 0.72,
        "legend": {
            "displayMode": "list",
            "placement": "bottom",
            "showLegend": True,
        },
        "orientation": "horizontal",
        "showValue": "always",
        "stacking": "normal",
        "tooltip": {"mode": "multi", "sort": "desc"},
        "xField": x_field,
        "xTickLabelMaxLength": 24,
        "xTickLabelRotation": 0,
        "xTickLabelSpacing": 0,
    }
    field_defaults["custom"] = {
        "axisGridShow": False,
        "axisLabel": "tokens",
        "axisPlacement": "auto",
        "fillOpacity": 72,
        "gradientMode": "none",
        "lineWidth": 1,
    }
    field_defaults["decimals"] = 0
    field_defaults["noValue"] = "0"
    field_defaults["unit"] = "short"
    _filter_visual_usage_fields(panel)


def _tune_heatmap_panel(
    panel: dict[str, Any],
    field_defaults: dict[str, Any],
    targets: list[dict[str, Any]],
) -> None:
    for target in targets:
        target["format"] = "heatmap"
    panel["options"] = {
        "calculate": False,
        "cellGap": 1,
        "color": {"mode": "scheme", "scheme": "Spectral", "steps": 64},
        "legend": {"show": True},
        "tooltip": {"show": True},
        "yAxis": {"axisPlacement": "left", "unit": "s"},
    }
    field_defaults["unit"] = "s"


def _tune_timeseries_panel(
    panel: dict[str, Any],
    field_defaults: dict[str, Any],
    targets: list[dict[str, Any]],
) -> None:
    panel["options"] = {
        "legend": {
            "displayMode": "table",
            "placement": "bottom",
            "showLegend": True,
        },
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    field_defaults["decimals"] = 2
    if _uses_span_duration(targets):
        field_defaults["unit"] = "s"


def _tune_table_panel(panel: dict[str, Any], field_defaults: dict[str, Any]) -> None:
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
            field_link_override("traceID", {"traceId": GRAFANA_FIELD_VALUE}),
            field_link_override(
                "spanID",
                {"traceId": GRAFANA_TRACE_ID_FIELD, "spanId": GRAFANA_FIELD_VALUE},
            ),
        ]
    )


def last_not_null_reduce_options() -> dict[str, Any]:
    return {"calcs": ["lastNotNull"], "fields": "", "values": False}


def field_link_override(field_name: str, trace_link: dict[str, str]) -> dict[str, Any]:
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


def trial_outcome_filter_link() -> dict[str, Any]:
    return {
        "title": "${__field.labels.outcome} trials",
        "url": trial_outcome_filter_url(),
        "targetBlank": False,
    }


def trial_outcome_filter_url() -> str:
    params = {
        "from": "${__from}",
        "to": "${__to}",
        f"var-{STUDY_ID_VARIABLE}": f"${STUDY_ID_VARIABLE}",
        f"var-{TRIAL_ID_VARIABLE}": "",
        f"var-{TRIAL_OUTCOME_VARIABLE}": "${__field.labels.outcome}",
        f"var-{AGENT_RUN_ID_VARIABLE}": "",
    }
    query = "&".join(f"{name}={quote(value)}" for name, value in params.items())
    for variable in [
        "${__from}",
        "${__to}",
        f"${STUDY_ID_VARIABLE}",
        "${__field.labels.outcome}",
    ]:
        query = query.replace(quote(variable), variable)

    return f"/d/agent-runtime-experiments/agent-runtime-experiments?{query}"


def _is_tempo_target(target: object) -> bool:
    if not isinstance(target, dict):
        return False

    datasource = target.get("datasource")
    return isinstance(datasource, dict) and datasource.get("uid") == TEMPO.uid


def _is_traceql_metrics_query(target: dict[str, Any]) -> bool:
    query = target.get("query")
    return isinstance(query, str) and any(
        function_name in query
        for function_name in ["sum_over_time(", "quantile_over_time("]
    )


def _is_traceql_select_query(target: dict[str, Any]) -> bool:
    query = target.get("query")
    return isinstance(query, str) and " | select(" in query


def _filter_visual_usage_fields(panel: dict[str, Any]) -> None:
    visual_fields = {
        11: [
            ("gen_ai.request.model", "Model"),
            ("gen_ai.usage.input_tokens", "Input tokens"),
            ("gen_ai.usage.output_tokens", "Output tokens"),
        ],
        12: [
            ("graph.node.name", "Graph node"),
            ("gen_ai.usage.input_tokens", "Input tokens"),
            ("gen_ai.usage.output_tokens", "Output tokens"),
        ],
        13: [
            ("gen_ai.request.model", "Model"),
            ("gen_ai.usage.cache_read.input_tokens", "Cache read tokens"),
            (
                "gen_ai.usage.cache_creation.input_tokens",
                "Cache creation tokens",
            ),
        ],
    }.get(panel.get("id"))
    if visual_fields is None:
        return

    panel["transformations"] = [
        {
            "id": "filterFieldsByName",
            "options": {
                "include": {"names": [field_name for field_name, _ in visual_fields]},
            },
        }
    ]
    panel.setdefault("fieldConfig", {}).setdefault("overrides", []).extend(
        [
            display_name_override(field_name, display_name)
            for field_name, display_name in visual_fields
            if field_name != _provider_usage_x_field(panel.get("id"))
        ]
    )


def _provider_usage_x_field(panel_id: object) -> str | None:
    return {
        11: "gen_ai.request.model",
        12: "graph.node.name",
        13: "gen_ai.request.model",
    }.get(panel_id)


def display_name_override(field_name: str, display_name: str) -> dict[str, Any]:
    return {
        "matcher": {"id": "byName", "options": field_name},
        "properties": [{"id": "displayName", "value": display_name}],
    }


def _uses_span_duration(targets: list[dict[str, Any]]) -> bool:
    for target in targets:
        query = target.get("query")
        if isinstance(query, str) and "span:duration" in query:
            return True
        expr = target.get("expr")
        if isinstance(expr, str) and "latency_bucket" in expr:
            return True

    return False
