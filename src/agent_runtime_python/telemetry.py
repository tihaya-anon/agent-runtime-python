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
