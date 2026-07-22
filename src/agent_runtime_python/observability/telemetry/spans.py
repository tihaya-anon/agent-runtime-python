"""OpenTelemetry span lifecycle helpers for Agent Run execution."""

from __future__ import annotations

import json
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
    MODEL_USAGE_ATTRIBUTE,
    USAGE_SNAPSHOT_ATTRIBUTES_BY_FIELD,
    agent_run_attributes,
    model_call_attributes,
)
from agent_runtime_python.observability.telemetry.context import (
    CURRENT_AGENT_RUN_ID,
    CURRENT_EXPERIMENT_STUDY_ID,
    CURRENT_EXPERIMENT_TARGET,
    CURRENT_EXPERIMENT_TRIAL_ID,
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
        agent_run_token = CURRENT_AGENT_RUN_ID.set(command["agentRunId"])
        study_token, trial_token, target_token = self._set_run_experiment_context(
            command
        )
        try:
            with self._tracer.start_as_current_span(
                "agent.run",
                attributes=agent_run_attributes(command),
            ) as span:
                yield span
        finally:
            CURRENT_EXPERIMENT_TARGET.reset(target_token)
            CURRENT_EXPERIMENT_TRIAL_ID.reset(trial_token)
            CURRENT_EXPERIMENT_STUDY_ID.reset(study_token)
            CURRENT_AGENT_RUN_ID.reset(agent_run_token)
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

        study_token = CURRENT_EXPERIMENT_STUDY_ID.set(study_id)
        trial_token = CURRENT_EXPERIMENT_TRIAL_ID.set(trial_id)
        target_token = CURRENT_EXPERIMENT_TARGET.set(target)
        try:
            with self._tracer.start_as_current_span(
                "experiment.trial",
                attributes=attributes,
            ) as span:
                yield span
        finally:
            CURRENT_EXPERIMENT_TARGET.reset(target_token)
            CURRENT_EXPERIMENT_TRIAL_ID.reset(trial_token)
            CURRENT_EXPERIMENT_STUDY_ID.reset(study_token)

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
        agent_run_id = CURRENT_AGENT_RUN_ID.get()
        study_id = CURRENT_EXPERIMENT_STUDY_ID.get()
        trial_id = CURRENT_EXPERIMENT_TRIAL_ID.get()
        target = CURRENT_EXPERIMENT_TARGET.get()
        with self._tracer.start_as_current_span(
            "gen_ai.inference.client",
            attributes=model_call_attributes(
                provider=provider,
                model=model,
                usage=usage,
                provider_finish_reason=provider_finish_reason,
                finish_reason=finish_reason,
                operation_name=operation_name,
                agent_run_id=agent_run_id,
                study_id=study_id,
                trial_id=trial_id,
                target=target,
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
        self._record_run_experiment_attributes(span)
        self._record_run_usage_snapshot_attributes(span)
        if terminal_event["type"] == "run.completed":
            span.set_status(Status(StatusCode.OK))
            span.set_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE, "succeeded")
            span.set_attribute(EXPERIMENT_OUTCOME_ATTRIBUTE, "succeeded")
            return

        if terminal_event["type"] == "run.cancelled":
            span.set_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE, "cancelled")
            span.set_attribute(EXPERIMENT_OUTCOME_ATTRIBUTE, "cancelled")
            return

        span.set_status(Status(StatusCode.ERROR))
        span.set_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE, "failed")
        span.set_attribute(EXPERIMENT_OUTCOME_ATTRIBUTE, "failed")
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

    def _set_run_experiment_context(self, command: dict[str, Any]):
        metadata = command.get("experimentMetadata")
        if not isinstance(metadata, dict):
            return (
                CURRENT_EXPERIMENT_STUDY_ID.set(CURRENT_EXPERIMENT_STUDY_ID.get()),
                CURRENT_EXPERIMENT_TRIAL_ID.set(CURRENT_EXPERIMENT_TRIAL_ID.get()),
                CURRENT_EXPERIMENT_TARGET.set(CURRENT_EXPERIMENT_TARGET.get()),
            )

        return (
            CURRENT_EXPERIMENT_STUDY_ID.set(str(metadata["studyId"])),
            CURRENT_EXPERIMENT_TRIAL_ID.set(str(metadata["trialId"])),
            CURRENT_EXPERIMENT_TARGET.set(str(metadata["target"])),
        )

    def _record_run_experiment_attributes(self, span: Span) -> None:
        study_id = CURRENT_EXPERIMENT_STUDY_ID.get()
        trial_id = CURRENT_EXPERIMENT_TRIAL_ID.get()
        target = CURRENT_EXPERIMENT_TARGET.get()
        if study_id:
            span.set_attribute(EXPERIMENT_STUDY_ID_ATTRIBUTE, study_id)
        if trial_id:
            span.set_attribute(EXPERIMENT_TRIAL_ID_ATTRIBUTE, trial_id)
        if target:
            span.set_attribute(EXPERIMENT_TARGET_ATTRIBUTE, target)

    def _record_run_usage_snapshot_attributes(self, span: Span) -> None:
        snapshot = self.usage_snapshot_event()
        if snapshot is None:
            return

        usage = snapshot["usage"]
        if isinstance(usage, dict):
            for field_name, value in usage.items():
                if isinstance(value, int):
                    attribute_name = USAGE_SNAPSHOT_ATTRIBUTES_BY_FIELD.get(field_name)
                    if attribute_name is not None:
                        span.set_attribute(attribute_name, value)
        model_usage = snapshot["modelUsage"]
        if isinstance(model_usage, list):
            span.set_attribute(
                MODEL_USAGE_ATTRIBUTE,
                json.dumps(model_usage, separators=(",", ":"), sort_keys=True),
            )
