"""OpenTelemetry helpers for Agent Run execution."""

from __future__ import annotations

import os
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Any

from openinference.semconv.trace import SpanAttributes
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, TracerProvider

from agent_runtime_python.observability.usage import ProviderUsage, UsageAccumulator

SERVICE_NAME = "agent-runtime-python"
AGENT_RUN_ID_ATTRIBUTE = SpanAttributes.SESSION_ID
AGENT_RUN_OUTCOME_ATTRIBUTE = "metadata.agent_run.outcome"
AGENT_RUN_ERROR_CLASSIFICATION_ATTRIBUTE = "metadata.agent_run.error_classification"
RUNTIME_PROFILE_ID_ATTRIBUTE = "metadata.runtime_profile.id"
EXPERIMENT_STUDY_ID_ATTRIBUTE = "metadata.experiment.study_id"
EXPERIMENT_TRIAL_ID_ATTRIBUTE = "metadata.experiment.trial_id"
EXPERIMENT_TARGET_ATTRIBUTE = "metadata.experiment.target"
EXPERIMENT_OUTCOME_ATTRIBUTE = "metadata.experiment.outcome"
GRAPH_ID_ATTRIBUTE = "metadata.agent_graph.id"
GRAPH_NODE_NAME_ATTRIBUTE = SpanAttributes.GRAPH_NODE_NAME
GEN_AI_SYSTEM_ATTRIBUTE = "gen_ai.system"
GEN_AI_OPERATION_NAME_ATTRIBUTE = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL_ATTRIBUTE = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL_ATTRIBUTE = "gen_ai.response.model"
GEN_AI_INPUT_TOKENS_ATTRIBUTE = "gen_ai.usage.input_tokens"
GEN_AI_OUTPUT_TOKENS_ATTRIBUTE = "gen_ai.usage.output_tokens"
GEN_AI_TOTAL_TOKENS_ATTRIBUTE = "gen_ai.usage.total_tokens"
GEN_AI_CACHE_READ_INPUT_TOKENS_ATTRIBUTE = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_CACHE_CREATION_INPUT_TOKENS_ATTRIBUTE = (
    "gen_ai.usage.cache_creation.input_tokens"
)
GEN_AI_REASONING_OUTPUT_TOKENS_ATTRIBUTE = "gen_ai.usage.reasoning.output_tokens"
GEN_AI_FINISH_REASONS_ATTRIBUTE = "gen_ai.response.finish_reasons"
GEN_AI_PROVIDER_FINISH_REASON_ATTRIBUTE = (
    "metadata.gen_ai.response.provider_finish_reason"
)
AGENT_BEHAVIOR_ATTRIBUTES = {
    "graph": "metadata.agent_behavior_version.graph",
    "state": "metadata.agent_behavior_version.state",
    "action": "metadata.agent_behavior_version.action",
    "prompt": "metadata.agent_behavior_version.prompt",
    "tool": "metadata.agent_behavior_version.tool",
    "model": "metadata.agent_behavior_version.model",
    "trialParameter": "metadata.agent_behavior_version.trial_parameter",
    "sourceRevision": "metadata.source_revision",
}

_TELEMETRY_CONFIGURED = False
_CURRENT_USAGE_ACCUMULATOR: ContextVar[UsageAccumulator | None] = ContextVar(
    "agent_runtime_usage_accumulator",
    default=None,
)
_CURRENT_GRAPH_ID: ContextVar[str | None] = ContextVar(
    "agent_runtime_graph_id",
    default=None,
)
_CURRENT_GRAPH_NODE_NAME: ContextVar[str | None] = ContextVar(
    "agent_runtime_graph_node_name",
    default=None,
)


def configure_telemetry_from_environment() -> None:
    """Configure OTLP trace export when standard OpenTelemetry env vars request it."""

    global _TELEMETRY_CONFIGURED
    if _TELEMETRY_CONFIGURED or not _otel_export_enabled():
        return

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", SERVICE_NAME),
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _TELEMETRY_CONFIGURED = True


def _otel_export_enabled() -> bool:
    if os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        return False

    traces_exporter = os.getenv("OTEL_TRACES_EXPORTER", "").lower()
    if traces_exporter in {"none", "console"}:
        return False

    return bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or traces_exporter)


def agent_run_attributes(command: dict[str, Any]) -> dict[str, str]:
    attributes = {
        AGENT_RUN_ID_ATTRIBUTE: command["agentRunId"],
        RUNTIME_PROFILE_ID_ATTRIBUTE: command["runtimeProfile"]["profileId"],
    }
    behavior_version = command.get("behaviorVersion", {})
    for dimension, attribute_name in AGENT_BEHAVIOR_ATTRIBUTES.items():
        value = behavior_version.get(dimension)
        if isinstance(value, str):
            attributes[attribute_name] = value

    return attributes


class AgentRunTelemetry:
    def __init__(self, tracer_provider: TracerProvider | None = None) -> None:
        self._tracer = trace.get_tracer(
            "agent_runtime_python.runtime.worker",
            tracer_provider=tracer_provider,
        )

    @contextmanager
    def start_run(self, command: dict[str, Any]):
        usage_token = _CURRENT_USAGE_ACCUMULATOR.set(UsageAccumulator())
        try:
            with self._tracer.start_as_current_span(
                "agent.run",
                attributes=agent_run_attributes(command),
            ) as span:
                yield span
        finally:
            _CURRENT_USAGE_ACCUMULATOR.reset(usage_token)

    @contextmanager
    def start_experiment_study(self, study_id: str, target: str):
        with self._tracer.start_as_current_span(
            "experiment.study",
            attributes={
                EXPERIMENT_STUDY_ID_ATTRIBUTE: study_id,
                EXPERIMENT_TARGET_ATTRIBUTE: target,
            },
        ) as span:
            yield span

    @contextmanager
    def start_experiment_trial(
        self,
        study_id: str,
        trial_id: str,
        target: str,
        parameters: dict[str, str | int | float | bool],
    ):
        attributes: dict[str, str | int | float | bool] = {
            EXPERIMENT_STUDY_ID_ATTRIBUTE: study_id,
            EXPERIMENT_TRIAL_ID_ATTRIBUTE: trial_id,
            EXPERIMENT_TARGET_ATTRIBUTE: target,
        }
        for name, value in parameters.items():
            attributes[f"metadata.experiment.parameter.{name}"] = value

        with self._tracer.start_as_current_span(
            "experiment.trial",
            attributes=attributes,
        ) as span:
            yield span

    @contextmanager
    def start_graph(self, graph_id: str):
        graph_token = _CURRENT_GRAPH_ID.set(graph_id)
        node_token = _CURRENT_GRAPH_NODE_NAME.set(None)
        try:
            with self._tracer.start_as_current_span(
                "agent.graph",
                attributes={GRAPH_ID_ATTRIBUTE: graph_id},
            ) as span:
                yield span
        finally:
            _CURRENT_GRAPH_NODE_NAME.reset(node_token)
            _CURRENT_GRAPH_ID.reset(graph_token)

    @contextmanager
    def start_graph_node(self, graph_id: str, node_name: str):
        graph_token = _CURRENT_GRAPH_ID.set(graph_id)
        node_token = _CURRENT_GRAPH_NODE_NAME.set(node_name)
        try:
            with self._tracer.start_as_current_span(
                "agent.graph.node",
                attributes={
                    GRAPH_ID_ATTRIBUTE: graph_id,
                    GRAPH_NODE_NAME_ATTRIBUTE: node_name,
                },
            ) as span:
                yield span
        finally:
            _CURRENT_GRAPH_NODE_NAME.reset(node_token)
            _CURRENT_GRAPH_ID.reset(graph_token)

    @contextmanager
    def start_model_call(
        self,
        *,
        provider: str,
        model: str,
        usage: ProviderUsage,
        provider_finish_reason: str | None = None,
        finish_reason: str | None = None,
        operation_name: str = "chat",
    ):
        graph_id = _CURRENT_GRAPH_ID.get()
        node_name = _CURRENT_GRAPH_NODE_NAME.get()
        with self._tracer.start_as_current_span(
            "gen_ai.inference.client",
            attributes=model_call_attributes(
                provider=provider,
                model=model,
                usage=usage,
                provider_finish_reason=provider_finish_reason,
                finish_reason=finish_reason,
                operation_name=operation_name,
                graph_id=graph_id,
                node_name=node_name,
            ),
        ) as span:
            try:
                yield span
            except Exception:
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                accumulator = _CURRENT_USAGE_ACCUMULATOR.get()
                if accumulator is not None:
                    accumulator.record(
                        provider=provider,
                        model=model,
                        usage=usage,
                        graph_id=graph_id,
                        node_name=node_name,
                    )

    def usage_snapshot_event(self) -> dict[str, Any] | None:
        accumulator = _CURRENT_USAGE_ACCUMULATOR.get()
        if accumulator is None:
            return None

        return accumulator.snapshot_event()

    def finish_run(self, span: Span, terminal_event: dict[str, Any]) -> None:
        if terminal_event["type"] == "run.completed":
            span.set_status(Status(StatusCode.OK))
            span.set_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE, "succeeded")
            return

        if terminal_event["type"] == "run.cancelled":
            span.set_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE, "cancelled")
            return

        span.set_status(Status(StatusCode.ERROR))
        span.set_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE, "failed")
        error_classification = terminal_event.get("errorClassification")
        if isinstance(error_classification, str):
            span.set_attribute(
                AGENT_RUN_ERROR_CLASSIFICATION_ATTRIBUTE, error_classification
            )

    def finish_experiment_trial(self, span: Span, outcome: str) -> None:
        if outcome == "failed":
            span.set_status(Status(StatusCode.ERROR))
        elif outcome == "succeeded":
            span.set_status(Status(StatusCode.OK))
        span.set_attribute(EXPERIMENT_OUTCOME_ATTRIBUTE, outcome)


def model_call_attributes(
    *,
    provider: str,
    model: str,
    usage: ProviderUsage,
    provider_finish_reason: str | None = None,
    finish_reason: str | None = None,
    operation_name: str = "chat",
    graph_id: str | None = None,
    node_name: str | None = None,
) -> dict[str, str | int | tuple[str, ...]]:
    normalized_finish_reason = finish_reason or normalize_finish_reason(
        provider_finish_reason
    )
    attributes: dict[str, str | int | tuple[str, ...]] = {
        GEN_AI_SYSTEM_ATTRIBUTE: provider,
        GEN_AI_OPERATION_NAME_ATTRIBUTE: operation_name,
        GEN_AI_REQUEST_MODEL_ATTRIBUTE: model,
        GEN_AI_RESPONSE_MODEL_ATTRIBUTE: model,
    }
    _set_usage_attribute(attributes, GEN_AI_INPUT_TOKENS_ATTRIBUTE, usage.input_tokens)
    _set_usage_attribute(
        attributes,
        GEN_AI_OUTPUT_TOKENS_ATTRIBUTE,
        usage.output_tokens,
    )
    _set_usage_attribute(attributes, GEN_AI_TOTAL_TOKENS_ATTRIBUTE, usage.total_tokens)
    _set_usage_attribute(
        attributes,
        GEN_AI_CACHE_READ_INPUT_TOKENS_ATTRIBUTE,
        usage.cached_input_tokens,
    )
    _set_usage_attribute(
        attributes,
        GEN_AI_CACHE_CREATION_INPUT_TOKENS_ATTRIBUTE,
        usage.cache_creation_input_tokens,
    )
    _set_usage_attribute(
        attributes,
        GEN_AI_REASONING_OUTPUT_TOKENS_ATTRIBUTE,
        usage.reasoning_output_tokens,
    )
    if provider_finish_reason:
        attributes[GEN_AI_PROVIDER_FINISH_REASON_ATTRIBUTE] = provider_finish_reason
    if normalized_finish_reason:
        attributes[GEN_AI_FINISH_REASONS_ATTRIBUTE] = (normalized_finish_reason,)
    if graph_id:
        attributes[GRAPH_ID_ATTRIBUTE] = graph_id
    if node_name:
        attributes[GRAPH_NODE_NAME_ATTRIBUTE] = node_name

    return attributes


def normalize_finish_reason(provider_finish_reason: str | None) -> str | None:
    if provider_finish_reason is None:
        return None

    reason = provider_finish_reason.strip().lower()
    if reason in {"stop", "stop_sequence", "end_turn"}:
        return "stop"
    if reason in {"length", "max_tokens", "max_output_tokens"}:
        return "length"
    if reason in {"tool_call", "tool_calls", "tool_use"}:
        return "tool_call"
    if reason in {"refusal", "content_filter", "safety"}:
        return "refusal"
    if reason in {"pause", "pause_turn"}:
        return "pause"
    if reason in {"error", "exception"}:
        return "error"

    return "unknown"


def _set_usage_attribute(
    attributes: dict[str, str | int | tuple[str, ...]],
    attribute_name: str,
    value: int | None,
) -> None:
    if value is not None:
        attributes[attribute_name] = value
