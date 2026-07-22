"""Provider Usage normalization and run-level aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_runtime_python.runtime.protocol import PROTOCOL_VERSION


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None

    def __post_init__(self) -> None:
        for value in _usage_values(self):
            if value is not None and value < 0:
                raise ValueError("Provider Usage token counts must not be negative")

        if (
            self.total_tokens is None
            and self.input_tokens is not None
            and self.output_tokens is not None
        ):
            object.__setattr__(
                self,
                "total_tokens",
                self.input_tokens + self.output_tokens,
            )

    @classmethod
    def empty(cls) -> "ProviderUsage":
        return cls()

    def is_empty(self) -> bool:
        return all(value is None for value in _usage_values(self))

    def add(self, other: "ProviderUsage") -> "ProviderUsage":
        return ProviderUsage(
            input_tokens=_sum_optional(self.input_tokens, other.input_tokens),
            output_tokens=_sum_optional(self.output_tokens, other.output_tokens),
            total_tokens=_sum_optional(self.total_tokens, other.total_tokens),
            cached_input_tokens=_sum_optional(
                self.cached_input_tokens,
                other.cached_input_tokens,
            ),
            cache_creation_input_tokens=_sum_optional(
                self.cache_creation_input_tokens,
                other.cache_creation_input_tokens,
            ),
            reasoning_output_tokens=_sum_optional(
                self.reasoning_output_tokens,
                other.reasoning_output_tokens,
            ),
        )

    def to_record(self) -> dict[str, int]:
        record = {}
        for attribute_name, field_name in _USAGE_RECORD_FIELDS:
            value = getattr(self, attribute_name)
            if isinstance(value, int):
                record[field_name] = value

        return record


@dataclass(frozen=True, order=True)
class ModelUsageKey:
    provider: str
    model: str
    graph_id: str | None = None
    node_name: str | None = None


class UsageAccumulator:
    def __init__(self) -> None:
        self._totals = ProviderUsage.empty()
        self._breakdown: dict[ModelUsageKey, ProviderUsage] = {}

    def record(
        self,
        *,
        provider: str,
        model: str,
        usage: ProviderUsage,
        graph_id: str | None = None,
        node_name: str | None = None,
    ) -> None:
        if usage.is_empty():
            return

        key = ModelUsageKey(
            provider=_required_text(provider, "provider"),
            model=_required_text(model, "model"),
            graph_id=_optional_text(graph_id),
            node_name=_optional_text(node_name),
        )
        self._totals = self._totals.add(usage)
        self._breakdown[key] = self._breakdown.get(
            key,
            ProviderUsage.empty(),
        ).add(usage)

    def snapshot_event(self) -> dict[str, Any] | None:
        if self._totals.is_empty():
            return None

        return {
            "version": PROTOCOL_VERSION,
            "type": "usage.snapshot",
            "usage": self._totals.to_record(),
            "modelUsage": [
                _model_usage_record(key, usage)
                for key, usage in sorted(self._breakdown.items())
            ],
        }


_USAGE_RECORD_FIELDS = (
    ("input_tokens", "inputTokens"),
    ("output_tokens", "outputTokens"),
    ("total_tokens", "totalTokens"),
    ("cached_input_tokens", "cachedInputTokens"),
    ("cache_creation_input_tokens", "cacheCreationInputTokens"),
    ("reasoning_output_tokens", "reasoningOutputTokens"),
)


def _usage_values(usage: ProviderUsage) -> tuple[int | None, ...]:
    return (
        usage.input_tokens,
        usage.output_tokens,
        usage.total_tokens,
        usage.cached_input_tokens,
        usage.cache_creation_input_tokens,
        usage.reasoning_output_tokens,
    )


def _sum_optional(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left

    return left + right


def _model_usage_record(
    key: ModelUsageKey,
    usage: ProviderUsage,
) -> dict[str, int | str]:
    record: dict[str, int | str] = {
        "provider": key.provider,
        "model": key.model,
    }
    if key.graph_id is not None:
        record["graphId"] = key.graph_id
    if key.node_name is not None:
        record["nodeName"] = key.node_name

    record.update(usage.to_record())
    return record


def _required_text(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"Model Usage {field_name} must not be empty")

    return value


def _optional_text(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None

    return value
