"""Pure provider-specific usage mappers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_runtime_python.observability.telemetry.attributes import (
    PROVIDER_TOOL_CALL_FINISH_REASONS,
    normalize_finish_reason,
)
from agent_runtime_python.observability.usage import ProviderUsage


@dataclass(frozen=True)
class ProviderUsageMapping:
    usage: ProviderUsage
    provider_finish_reason: str | None = None
    finish_reason: str | None = None


def map_openai_responses_usage(response: object) -> ProviderUsageMapping:
    """Map an OpenAI Responses response or response event into Provider Usage."""

    response = _openai_response_payload(response)
    usage = _field(response, "usage")
    provider_finish_reason = _openai_provider_finish_reason(response)
    status = _text_field(response, "status")

    return ProviderUsageMapping(
        usage=ProviderUsage(
            input_tokens=_int_field(usage, "input_tokens"),
            output_tokens=_int_field(usage, "output_tokens"),
            total_tokens=_int_field(usage, "total_tokens"),
            cached_input_tokens=_int_field(
                _field(usage, "input_tokens_details"),
                "cached_tokens",
            ),
            reasoning_output_tokens=_int_field(
                _field(usage, "output_tokens_details"),
                "reasoning_tokens",
            ),
            estimate_total=False,
        ),
        provider_finish_reason=provider_finish_reason,
        finish_reason=_normalized_finish_reason(
            provider_finish_reason,
            provider_status=status,
        ),
    )


def map_anthropic_messages_usage(message: object) -> ProviderUsageMapping:
    """Map an Anthropic Messages response into Provider Usage."""

    usage = _field(message, "usage")
    provider_finish_reason = _text_field(message, "stop_reason")

    return ProviderUsageMapping(
        usage=ProviderUsage(
            input_tokens=_int_field(usage, "input_tokens"),
            output_tokens=_int_field(usage, "output_tokens"),
            cached_input_tokens=_int_field(usage, "cache_read_input_tokens"),
            cache_creation_input_tokens=_int_field(
                usage,
                "cache_creation_input_tokens",
            ),
            estimate_total=False,
        ),
        provider_finish_reason=provider_finish_reason,
        finish_reason=normalize_finish_reason(provider_finish_reason),
    )


def _openai_response_payload(response: object) -> object:
    event_type = _text_field(response, "type")
    nested_response = _field(response, "response")
    if event_type is not None and event_type.startswith("response."):
        return nested_response if nested_response is not None else response

    return response


def _openai_provider_finish_reason(response: object) -> str | None:
    status = _text_field(response, "status")
    error = _field(response, "error")
    error_reason = _text_field(error, "code") or _text_field(error, "type")
    if status in {"failed", "cancelled"}:
        return error_reason or status
    if error_reason is not None:
        return error_reason

    incomplete_reason = _text_field(_field(response, "incomplete_details"), "reason")
    if incomplete_reason is not None:
        return incomplete_reason

    output_reason = _openai_output_finish_reason(_field(response, "output"))
    if output_reason is not None:
        return output_reason

    return status


def _openai_output_finish_reason(output: object) -> str | None:
    for item in _iter_sequence(output):
        item_type = _text_field(item, "type")
        if item_type in PROVIDER_TOOL_CALL_FINISH_REASONS:
            return item_type
        if _message_contains_refusal(item):
            return "refusal"

    return None


def _message_contains_refusal(message: object) -> bool:
    if _text_field(message, "type") != "message":
        return False

    for content_item in _iter_sequence(_field(message, "content")):
        if _text_field(content_item, "type") == "refusal":
            return True
        if _text_field(content_item, "refusal") is not None:
            return True

    return False


def _normalized_finish_reason(
    provider_finish_reason: str | None,
    *,
    provider_status: str | None,
) -> str | None:
    if provider_status in {"failed", "cancelled"}:
        return "error"
    if provider_status in {"queued", "in_progress"}:
        return "pause"

    return normalize_finish_reason(provider_finish_reason)


def _field(value: object, field_name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field_name)
    if value is None:
        return None

    return getattr(value, field_name, None)


def _text_field(value: object, field_name: str) -> str | None:
    field_value = _field(value, field_name)
    if isinstance(field_value, str):
        stripped = field_value.strip()
        if stripped:
            return stripped

    return None


def _int_field(value: object, field_name: str) -> int | None:
    field_value = _field(value, field_name)
    if isinstance(field_value, int) and not isinstance(field_value, bool):
        return field_value

    return None


def _iter_sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return value

    return ()
