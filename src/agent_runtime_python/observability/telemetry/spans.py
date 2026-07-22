"""OpenTelemetry span lifecycle helpers for Agent Run execution."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, TracerProvider

from agent_runtime_python.observability.telemetry.attributes import (
    AGENT_RUN_ERROR_CLASSIFICATION_ATTRIBUTE,
    AGENT_RUN_OUTCOME_ATTRIBUTE,
    EXPERIMENT_OUTCOME_ATTRIBUTE,
    EXPERIMENT_STUDY_ID_ATTRIBUTE,
    EXPERIMENT_TARGET_ATTRIBUTE,
    EXPERIMENT_TRIAL_ID_ATTRIBUTE,
    GRAPH_ID_ATTRIBUTE,
    GRAPH_NODE_NAME_ATTRIBUTE,
    agent_run_attributes,
    model_call_attributes,
)
from agent_runtime_python.observability.telemetry.context import (
    CURRENT_GRAPH_ID,
    CURRENT_GRAPH_NODE_NAME,
    CURRENT_USAGE_ACCUMULATOR,
)
from agent_runtime_python.observability.usage import ProviderUsage, UsageAccumulator


class AgentRunTelemetry:
    def __init__(self, tracer_provider: TracerProvider | None = None) -> None:
        self._tracer = trace.get_tracer(
            "agent_runtime_python.runtime.worker",
            tracer_provider=tracer_provider,
        )

    @contextmanager
    def start_run(self, command: dict[str, Any]):
        usage_token = CURRENT_USAGE_ACCUMULATOR.set(UsageAccumulator())
        try:
            with self._tracer.start_as_current_span(
                "agent.run",
                attributes=agent_run_attributes(command),
            ) as span:
                yield span
        finally:
            CURRENT_USAGE_ACCUMULATOR.reset(usage_token)

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
        graph_token = CURRENT_GRAPH_ID.set(graph_id)
        node_token = CURRENT_GRAPH_NODE_NAME.set(None)
        try:
            with self._tracer.start_as_current_span(
                "agent.graph",
                attributes={GRAPH_ID_ATTRIBUTE: graph_id},
            ) as span:
                yield span
        finally:
            CURRENT_GRAPH_NODE_NAME.reset(node_token)
            CURRENT_GRAPH_ID.reset(graph_token)

    @contextmanager
    def start_graph_node(self, graph_id: str, node_name: str):
        graph_token = CURRENT_GRAPH_ID.set(graph_id)
        node_token = CURRENT_GRAPH_NODE_NAME.set(node_name)
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
            CURRENT_GRAPH_NODE_NAME.reset(node_token)
            CURRENT_GRAPH_ID.reset(graph_token)

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
        graph_id = CURRENT_GRAPH_ID.get()
        node_name = CURRENT_GRAPH_NODE_NAME.get()
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
                accumulator = CURRENT_USAGE_ACCUMULATOR.get()
                if accumulator is not None:
                    accumulator.record(
                        provider=provider,
                        model=model,
                        usage=usage,
                        graph_id=graph_id,
                        node_name=node_name,
                    )

    def usage_snapshot_event(self) -> dict[str, Any] | None:
        accumulator = CURRENT_USAGE_ACCUMULATOR.get()
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
