"""OpenTelemetry helpers for Agent Run worker execution."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span

AGENT_RUN_ID_ATTRIBUTE = "session.id"
AGENT_RUN_OUTCOME_ATTRIBUTE = "metadata.agent_run.outcome"
AGENT_RUN_ERROR_CLASSIFICATION_ATTRIBUTE = "metadata.agent_run.error_classification"
RUNTIME_PROFILE_ID_ATTRIBUTE = "metadata.runtime_profile.id"
EXPERIMENT_STUDY_ID_ATTRIBUTE = "metadata.experiment.study_id"
EXPERIMENT_TRIAL_ID_ATTRIBUTE = "metadata.experiment.trial_id"
EXPERIMENT_TARGET_ATTRIBUTE = "metadata.experiment.target"
EXPERIMENT_OUTCOME_ATTRIBUTE = "metadata.experiment.outcome"
GRAPH_ID_ATTRIBUTE = "metadata.agent_graph.id"
GRAPH_NODE_NAME_ATTRIBUTE = "metadata.agent_graph.node"
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
    def __init__(self) -> None:
        self._tracer = trace.get_tracer("agent_runtime_python.worker")

    @contextmanager
    def start_run(self, command: dict[str, Any]):
        with self._tracer.start_as_current_span(
            "agent.run",
            attributes=agent_run_attributes(command),
        ) as span:
            yield span

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
        with self._tracer.start_as_current_span(
            "agent.graph",
            attributes={GRAPH_ID_ATTRIBUTE: graph_id},
        ) as span:
            yield span

    @contextmanager
    def start_graph_node(self, graph_id: str, node_name: str):
        with self._tracer.start_as_current_span(
            "agent.graph.node",
            attributes={
                GRAPH_ID_ATTRIBUTE: graph_id,
                GRAPH_NODE_NAME_ATTRIBUTE: node_name,
            },
        ) as span:
            yield span

    def finish_run(self, span: Span, terminal_event: dict[str, Any]) -> None:
        if terminal_event["type"] == "run.completed":
            span.set_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE, "succeeded")
            return

        if terminal_event["type"] == "run.cancelled":
            span.set_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE, "cancelled")
            return

        span.set_attribute(AGENT_RUN_OUTCOME_ATTRIBUTE, "failed")
        error_classification = terminal_event.get("errorClassification")
        if isinstance(error_classification, str):
            span.set_attribute(
                AGENT_RUN_ERROR_CLASSIFICATION_ATTRIBUTE, error_classification
            )

    def finish_experiment_trial(self, span: Span, outcome: str) -> None:
        span.set_attribute(EXPERIMENT_OUTCOME_ATTRIBUTE, outcome)
