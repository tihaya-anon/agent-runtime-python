"""OpenTelemetry attribute names and mapping helpers."""

from __future__ import annotations

from typing import Any

from openinference.semconv.trace import SpanAttributes

from agent_runtime_python.observability.usage import ProviderUsage

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
