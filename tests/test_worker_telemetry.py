import json
import unittest

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from agent_runtime_python.observability.telemetry import (
    AGENT_BEHAVIOR_ATTRIBUTES,
    AGENT_RUN_ID_ATTRIBUTE,
    GEN_AI_CACHE_CREATION_INPUT_TOKENS_ATTRIBUTE,
    GEN_AI_CACHE_READ_INPUT_TOKENS_ATTRIBUTE,
    GEN_AI_FINISH_REASONS_ATTRIBUTE,
    GEN_AI_INPUT_TOKENS_ATTRIBUTE,
    GEN_AI_OPERATION_NAME_ATTRIBUTE,
    GEN_AI_OUTPUT_TOKENS_ATTRIBUTE,
    GEN_AI_PROVIDER_FINISH_REASON_ATTRIBUTE,
    GEN_AI_REASONING_OUTPUT_TOKENS_ATTRIBUTE,
    GEN_AI_REQUEST_MODEL_ATTRIBUTE,
    GEN_AI_SYSTEM_ATTRIBUTE,
    GEN_AI_TOTAL_TOKENS_ATTRIBUTE,
    GRAPH_ID_ATTRIBUTE,
    GRAPH_NODE_NAME_ATTRIBUTE,
    RUNTIME_PROFILE_ID_ATTRIBUTE,
    AgentRunTelemetry,
    agent_run_attributes,
)
from agent_runtime_python.observability.usage import ProviderUsage

from tests.worker_helpers import VALID_START_COMMAND, tracer_provider


class WorkerTelemetryTest(unittest.TestCase):
    def test_worker_telemetry_attributes_align_with_ts_agent_run_names(self) -> None:
        command = json.loads(VALID_START_COMMAND)

        attributes = agent_run_attributes(command)

        self.assertEqual(attributes[AGENT_RUN_ID_ATTRIBUTE], "ar_python_smoke")
        self.assertEqual(
            attributes[RUNTIME_PROFILE_ID_ATTRIBUTE], "runtime-development"
        )
        self.assertEqual(
            attributes[AGENT_BEHAVIOR_ATTRIBUTES["graph"]],
            "graph:python-smoke",
        )

    def test_graph_telemetry_constants_have_bounded_attribute_names(self) -> None:
        self.assertEqual(GRAPH_ID_ATTRIBUTE, "metadata.agent_graph.id")
        self.assertEqual(GRAPH_NODE_NAME_ATTRIBUTE, "graph.node.name")

    def test_agent_run_telemetry_marks_completed_runs_ok(self) -> None:
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        with telemetry.start_run(json.loads(VALID_START_COMMAND)) as span:
            telemetry.finish_run(span, {"type": "run.completed"})

        finished_span = exporter.get_finished_spans()[0]
        self.assertEqual(finished_span.status.status_code, StatusCode.OK)

    def test_agent_run_telemetry_marks_failed_runs_error(self) -> None:
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        with telemetry.start_run(json.loads(VALID_START_COMMAND)) as span:
            telemetry.finish_run(
                span,
                {"type": "run.failed", "errorClassification": "validation"},
            )

        finished_span = exporter.get_finished_spans()[0]
        self.assertEqual(finished_span.status.status_code, StatusCode.ERROR)

    def test_model_call_telemetry_records_genai_usage_and_graph_node_context(
        self,
    ) -> None:
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        with telemetry.start_run(json.loads(VALID_START_COMMAND)):
            with telemetry.start_graph("graph:custom"):
                with telemetry.start_graph_node("graph:custom", "draft_response"):
                    with telemetry.start_model_call(
                        provider="synthetic",
                        model="model:test",
                        usage=ProviderUsage(
                            input_tokens=5,
                            output_tokens=3,
                            cached_input_tokens=2,
                            cache_creation_input_tokens=1,
                            reasoning_output_tokens=1,
                        ),
                        provider_finish_reason="stop_sequence",
                        finish_reason="stop",
                    ):
                        pass
            snapshot = telemetry.usage_snapshot_event()

        self.assertEqual(
            snapshot,
            {
                "version": 1,
                "type": "usage.snapshot",
                "usage": {
                    "inputTokens": 5,
                    "outputTokens": 3,
                    "totalTokens": 8,
                    "cachedInputTokens": 2,
                    "cacheCreationInputTokens": 1,
                    "reasoningOutputTokens": 1,
                },
                "modelUsage": [
                    {
                        "provider": "synthetic",
                        "model": "model:test",
                        "graphId": "graph:custom",
                        "nodeName": "draft_response",
                        "inputTokens": 5,
                        "outputTokens": 3,
                        "totalTokens": 8,
                        "cachedInputTokens": 2,
                        "cacheCreationInputTokens": 1,
                        "reasoningOutputTokens": 1,
                    },
                ],
            },
        )
        attributes = model_span_attributes(exporter)
        self.assertEqual(attributes[GEN_AI_SYSTEM_ATTRIBUTE], "synthetic")
        self.assertEqual(attributes[GEN_AI_OPERATION_NAME_ATTRIBUTE], "chat")
        self.assertEqual(attributes[GEN_AI_REQUEST_MODEL_ATTRIBUTE], "model:test")
        self.assertEqual(attributes[GEN_AI_INPUT_TOKENS_ATTRIBUTE], 5)
        self.assertEqual(attributes[GEN_AI_OUTPUT_TOKENS_ATTRIBUTE], 3)
        self.assertEqual(attributes[GEN_AI_TOTAL_TOKENS_ATTRIBUTE], 8)
        self.assertEqual(attributes[GEN_AI_CACHE_READ_INPUT_TOKENS_ATTRIBUTE], 2)
        self.assertEqual(attributes[GEN_AI_CACHE_CREATION_INPUT_TOKENS_ATTRIBUTE], 1)
        self.assertEqual(attributes[GEN_AI_REASONING_OUTPUT_TOKENS_ATTRIBUTE], 1)
        self.assertEqual(
            attributes[GEN_AI_PROVIDER_FINISH_REASON_ATTRIBUTE], "stop_sequence"
        )
        self.assertEqual(attributes[GEN_AI_FINISH_REASONS_ATTRIBUTE], ("stop",))
        self.assertEqual(attributes[GRAPH_ID_ATTRIBUTE], "graph:custom")
        self.assertEqual(attributes[GRAPH_NODE_NAME_ATTRIBUTE], "draft_response")

    def test_model_usage_snapshot_accumulates_and_groups_observed_usage(self) -> None:
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        with telemetry.start_run(json.loads(VALID_START_COMMAND)):
            with telemetry.start_model_call(
                provider="synthetic",
                model="model:a",
                usage=ProviderUsage(input_tokens=1, output_tokens=2),
            ):
                pass
            with telemetry.start_model_call(
                provider="synthetic",
                model="model:a",
                usage=ProviderUsage(input_tokens=3, output_tokens=4),
            ):
                pass
            with telemetry.start_model_call(
                provider="synthetic",
                model="model:b",
                usage=ProviderUsage(input_tokens=5, output_tokens=6),
            ):
                pass
            snapshot = telemetry.usage_snapshot_event()

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(
            snapshot["usage"],
            {"inputTokens": 9, "outputTokens": 12, "totalTokens": 21},
        )
        self.assertEqual(
            snapshot["modelUsage"],
            [
                {
                    "provider": "synthetic",
                    "model": "model:a",
                    "inputTokens": 4,
                    "outputTokens": 6,
                    "totalTokens": 10,
                },
                {
                    "provider": "synthetic",
                    "model": "model:b",
                    "inputTokens": 5,
                    "outputTokens": 6,
                    "totalTokens": 11,
                },
            ],
        )

    def test_model_call_telemetry_accumulates_usage_when_call_raises(self) -> None:
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        with telemetry.start_run(json.loads(VALID_START_COMMAND)):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                with telemetry.start_model_call(
                    provider="synthetic",
                    model="model:failing",
                    usage=ProviderUsage(input_tokens=2, output_tokens=1),
                ):
                    raise RuntimeError("synthetic failure")
            snapshot = telemetry.usage_snapshot_event()

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(
            snapshot["usage"],
            {"inputTokens": 2, "outputTokens": 1, "totalTokens": 3},
        )
        model_span = next(
            span
            for span in exporter.get_finished_spans()
            if span.name == "gen_ai.inference.client"
        )
        self.assertEqual(model_span.status.status_code, StatusCode.ERROR)


def model_span_attributes(exporter: InMemorySpanExporter):
    model_span = next(
        span
        for span in exporter.get_finished_spans()
        if span.name == "gen_ai.inference.client"
    )
    attributes = model_span.attributes
    assert attributes is not None
    return attributes


if __name__ == "__main__":
    unittest.main()
