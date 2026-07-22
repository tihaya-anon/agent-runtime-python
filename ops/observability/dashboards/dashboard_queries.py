"""TraceQL and PromQL query builders for the experiments dashboard."""

from __future__ import annotations

from agent_runtime_python.observability.telemetry import (
    AGENT_RUN_ID_ATTRIBUTE,
    AGENT_RUN_OUTCOME_ATTRIBUTE,
    EXPERIMENT_OUTCOME_ATTRIBUTE,
    EXPERIMENT_STUDY_ID_ATTRIBUTE,
    EXPERIMENT_TARGET_ATTRIBUTE,
    EXPERIMENT_TRIAL_ID_ATTRIBUTE,
)

SERVICE_NAME = "agent-runtime-python"
STUDY_ID_VARIABLE = "study_id"
TRIAL_ID_VARIABLE = "trial_id"
TRIAL_OUTCOME_VARIABLE = "trial_outcome"
AGENT_RUN_ID_VARIABLE = "agent_run_id"
AGENT_GRAPH_NODE_SPAN = "agent.graph.node"
AGENT_GRAPH_SPAN = "agent.graph"
AGENT_RUN_SPAN = "agent.run"
EXPERIMENT_TRIAL_SPAN = "experiment.trial"
SPANMETRICS_CALLS_TOTAL = "traces_spanmetrics_calls_total"
SPANMETRICS_LATENCY_BUCKET = "traces_spanmetrics_latency_bucket"
SPANMETRICS_WINDOW = "5m"


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
        f"&& {selected_filter(EXPERIMENT_OUTCOME_ATTRIBUTE, TRIAL_OUTCOME_VARIABLE)} "
        f"&& {selected_filter(AGENT_RUN_ID_ATTRIBUTE, AGENT_RUN_ID_VARIABLE)} "
        f"}} | {fields}"
    )


def trial_rate_promql() -> str:
    succeeded = trial_rate_by_status_promql("STATUS_CODE_OK")
    failed = trial_rate_by_status_promql("STATUS_CODE_ERROR")
    return (
        "sum by (outcome) ("
        f"{span_status_outcome_promql(succeeded, 'succeeded')} "
        "or "
        f"{span_status_outcome_promql(failed, 'failed')}"
        ")"
    )


def trial_starts_per_min_promql() -> str:
    return _span_rate_per_min(EXPERIMENT_TRIAL_MATCHER)


def failed_runs_per_min_promql() -> str:
    return _span_rate_per_min(f'{AGENT_RUN_MATCHER},status_code="STATUS_CODE_ERROR"')


def trial_error_ratio_promql() -> str:
    errored = _span_rate(f'{EXPERIMENT_TRIAL_MATCHER},status_code="STATUS_CODE_ERROR"')
    total = _span_rate(EXPERIMENT_TRIAL_MATCHER)
    return f"100 * {errored} / clamp_min({total}, 0.001)"


def trial_outcome_mix_promql() -> str:
    succeeded = trial_increase_by_status_promql("STATUS_CODE_OK")
    failed = trial_increase_by_status_promql("STATUS_CODE_ERROR")
    return (
        "sum by (outcome) ("
        f"{span_status_outcome_promql(succeeded, 'succeeded')} "
        "or "
        f"{span_status_outcome_promql(failed, 'failed')}"
        ")"
    )


def runtime_activity_mix_promql() -> str:
    return (
        "sum by (span_name) "
        f"(increase({SPANMETRICS_CALLS_TOTAL}"
        f'{{service="{SERVICE_NAME}",span_name=~"{runtime_span_regex()}"}}'
        "[$__range]))"
    )


def agent_run_duration_p95_promql() -> str:
    return _duration_p95(AGENT_RUN_MATCHER)


def duration_p95_by_span_promql() -> str:
    return _duration_p95(
        f'service="{SERVICE_NAME}",span_name=~"{runtime_span_regex()}"'
    )


def agent_run_latency_distribution_promql() -> str:
    return (
        "sum by (le) "
        f"(rate({SPANMETRICS_LATENCY_BUCKET}{{{AGENT_RUN_MATCHER}}}"
        f"[{SPANMETRICS_WINDOW}]))"
    )


def trial_rate_by_status_promql(status_code: str) -> str:
    return _span_rate_per_min(f'{EXPERIMENT_TRIAL_MATCHER},status_code="{status_code}"')


def trial_increase_by_status_promql(status_code: str) -> str:
    return (
        f"increase({SPANMETRICS_CALLS_TOTAL}"
        f'{{{EXPERIMENT_TRIAL_MATCHER},status_code="{status_code}"}}'
        "[$__range])"
    )


def span_attribute(name: str) -> str:
    return f'span."{name}"'


def selected_filter(attribute_name: str, variable_name: str) -> str:
    template = f"${variable_name}"
    return f'({span_attribute(attribute_name)} = "{template}" || "{template}" = "")'


def span_status_outcome_promql(expr: str, outcome: str) -> str:
    return f'label_replace({expr}, "outcome", "{outcome}", "status_code", ".*")'


def select_fields(fields: list[str]) -> str:
    return f"select({', '.join(fields)})"


def runtime_span_regex() -> str:
    return (
        f"{EXPERIMENT_TRIAL_SPAN}|{AGENT_RUN_SPAN}|"
        f"{AGENT_GRAPH_SPAN}|{AGENT_GRAPH_NODE_SPAN}"
    )


def _span_rate(matcher: str) -> str:
    return (
        f"sum(rate({SPANMETRICS_CALLS_TOTAL}" f"{{{matcher}}}[{SPANMETRICS_WINDOW}]))"
    )


def _span_rate_per_min(matcher: str) -> str:
    return (
        f"sum(rate({SPANMETRICS_CALLS_TOTAL}"
        f"{{{matcher}}}[{SPANMETRICS_WINDOW}]) * 60)"
    )


def _duration_p95(matcher: str) -> str:
    return (
        "histogram_quantile(0.95, sum by (le, span_name) "
        f"(rate({SPANMETRICS_LATENCY_BUCKET}"
        f"{{{matcher}}}[{SPANMETRICS_WINDOW}])))"
    )


EXPERIMENT_TRIAL_MATCHER = (
    f'service="{SERVICE_NAME}",span_name="{EXPERIMENT_TRIAL_SPAN}"'
)
AGENT_RUN_MATCHER = f'service="{SERVICE_NAME}",span_name="{AGENT_RUN_SPAN}"'
