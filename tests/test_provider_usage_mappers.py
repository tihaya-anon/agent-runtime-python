from types import SimpleNamespace
import unittest

from agent_runtime_python.observability.provider_mappers import (
    map_anthropic_messages_usage,
    map_openai_responses_usage,
)
from agent_runtime_python.observability.usage import ProviderUsage, UsageAccumulator


class ProviderUsageMapperTest(unittest.TestCase):
    def test_openai_responses_maps_usage_and_completed_finish_reason(self) -> None:
        mapped = map_openai_responses_usage(
            {
                "status": "completed",
                "usage": {
                    "input_tokens": 15,
                    "output_tokens": 8,
                    "total_tokens": 23,
                    "input_tokens_details": {"cached_tokens": 4},
                    "output_tokens_details": {"reasoning_tokens": 3},
                },
            }
        )

        self.assertEqual(
            mapped.usage,
            ProviderUsage(
                input_tokens=15,
                output_tokens=8,
                total_tokens=23,
                cached_input_tokens=4,
                reasoning_output_tokens=3,
            ),
        )
        self.assertEqual(mapped.provider_finish_reason, "completed")
        self.assertEqual(mapped.finish_reason, "stop")

    def test_openai_responses_keeps_missing_numeric_fields_absent(self) -> None:
        mapped = map_openai_responses_usage(
            SimpleNamespace(
                status="completed",
                usage=SimpleNamespace(input_tokens=15, output_tokens=8),
            )
        )

        self.assertEqual(
            mapped.usage,
            ProviderUsage.from_provider_report(input_tokens=15, output_tokens=8),
        )
        self.assertEqual(mapped.usage.total_tokens, None)
        self.assertEqual(mapped.usage.cached_input_tokens, None)
        self.assertEqual(mapped.usage.reasoning_output_tokens, None)

    def test_openai_responses_normalizes_provider_finish_reasons(self) -> None:
        cases = [
            (
                {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
                "max_output_tokens",
                "length",
            ),
            (
                {
                    "status": "completed",
                    "output": [{"type": "function_call"}],
                },
                "function_call",
                "tool_call",
            ),
            (
                {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "refusal", "refusal": "No."}],
                        }
                    ],
                },
                "refusal",
                "refusal",
            ),
            (
                {"status": "failed", "error": {"code": "server_error"}},
                "server_error",
                "error",
            ),
        ]

        for response, provider_finish_reason, finish_reason in cases:
            with self.subTest(finish_reason=provider_finish_reason):
                mapped = map_openai_responses_usage(response)

                self.assertEqual(
                    mapped.provider_finish_reason,
                    provider_finish_reason,
                )
                self.assertEqual(mapped.finish_reason, finish_reason)

    def test_anthropic_messages_maps_usage_and_stop_reason(self) -> None:
        mapped = map_anthropic_messages_usage(
            SimpleNamespace(
                stop_reason="end_turn",
                usage=SimpleNamespace(
                    input_tokens=12,
                    output_tokens=7,
                    cache_creation_input_tokens=5,
                    cache_read_input_tokens=3,
                ),
            )
        )

        self.assertEqual(
            mapped.usage,
            ProviderUsage.from_provider_report(
                input_tokens=12,
                output_tokens=7,
                cache_creation_input_tokens=5,
                cached_input_tokens=3,
            ),
        )
        self.assertEqual(mapped.usage.total_tokens, None)
        self.assertEqual(mapped.provider_finish_reason, "end_turn")
        self.assertEqual(mapped.finish_reason, "stop")

    def test_anthropic_messages_keeps_missing_numeric_fields_absent(self) -> None:
        mapped = map_anthropic_messages_usage(
            {
                "stop_reason": "max_tokens",
                "usage": {
                    "input_tokens": 12,
                },
            }
        )

        self.assertEqual(
            mapped.usage,
            ProviderUsage.from_provider_report(input_tokens=12),
        )
        self.assertEqual(mapped.usage.output_tokens, None)
        self.assertEqual(mapped.usage.total_tokens, None)
        self.assertEqual(mapped.usage.cache_creation_input_tokens, None)
        self.assertEqual(mapped.usage.cached_input_tokens, None)
        self.assertEqual(mapped.provider_finish_reason, "max_tokens")
        self.assertEqual(mapped.finish_reason, "length")

    def test_mapped_usage_keeps_missing_total_absent_when_accumulated(self) -> None:
        mapped = map_anthropic_messages_usage(
            {
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 7,
                },
            }
        )
        accumulator = UsageAccumulator()

        accumulator.record(
            provider="anthropic",
            model="claude-test",
            usage=mapped.usage,
        )

        snapshot = accumulator.snapshot_event()
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["usage"], {"inputTokens": 12, "outputTokens": 7})
        self.assertEqual(
            snapshot["modelUsage"],
            [
                {
                    "provider": "anthropic",
                    "model": "claude-test",
                    "inputTokens": 12,
                    "outputTokens": 7,
                }
            ],
        )

    def test_anthropic_messages_normalizes_low_cardinality_stop_reasons(self) -> None:
        cases = {
            "stop_sequence": "stop",
            "tool_use": "tool_call",
            "refusal": "refusal",
            "pause_turn": "pause",
            "model_context_window_exceeded": "length",
            "error": "error",
        }

        for stop_reason, finish_reason in cases.items():
            with self.subTest(stop_reason=stop_reason):
                mapped = map_anthropic_messages_usage({"stop_reason": stop_reason})

                self.assertEqual(mapped.provider_finish_reason, stop_reason)
                self.assertEqual(mapped.finish_reason, finish_reason)


if __name__ == "__main__":
    unittest.main()
