import json
import unittest
from io import StringIO
from typing import Any

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from agent_runtime_python import __version__
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
from agent_runtime_python.runtime.protocol import EVENT_VALIDATOR
from agent_runtime_python.runtime.worker import AgentRunWorker, main, run_worker

VALID_START_COMMAND = (
    '{"version":1,'
    '"type":"run.start",'
    '"agentRunId":"ar_python_smoke",'
    '"input":{"message":"Explain closures."},'
    '"runtimeProfile":{'
    '"schemaVersion":1,'
    '"profileId":"runtime-development",'
    '"runtimePolicy":{'
    '"agentBehaviorVersion":{'
    '"policy":"development",'
    '"requireCompleteDimensions":false,'
    '"rejectUnresolvedDimensions":false,'
    '"allowIncompleteAdHocRuns":true,'
    '"incompleteAdHocRuns":{"comparable":false,"promotable":false}'
    "},"
    '"sourceRevision":{"requireCleanForPublishedGraphVersions":false}'
    "}"
    "},"
    '"behaviorVersion":{"graph":"graph:python-smoke"}'
    "}\n"
)


def _start_command_for_graph(graph_id: str) -> str:
    command = json.loads(VALID_START_COMMAND)
    command["behaviorVersion"]["graph"] = graph_id
    return json.dumps(command) + "\n"


def _decode_events(output: str) -> list[dict[str, Any]]:
    events = [json.loads(line) for line in output.splitlines()]
    for event in events:
        EVENT_VALIDATOR.validate(event)

    return events


class WorkerTest(unittest.TestCase):
    def test_package_exposes_version(self) -> None:
        # Given
        version = __version__

        # When
        has_version = bool(version)

        # Then
        self.assertTrue(has_version)

    def test_worker_entrypoint_exits_successfully(self) -> None:
        # Given
        expected_exit_code = 0
        output = StringIO()

        # When
        exit_code = main([], output)

        # Then
        self.assertEqual(exit_code, expected_exit_code)

    def test_worker_executes_smoke_graph_for_valid_start_command(self) -> None:
        # Given
        worker = AgentRunWorker()

        # When
        events = worker.handle_line(VALID_START_COMMAND)

        # Then
        for event in events:
            EVENT_VALIDATOR.validate(event)
        self.assertEqual(
            [event["type"] for event in events],
            [
                "run.started",
                "progress.update",
                "message.delta",
                "progress.update",
                "run.completed",
            ],
        )
        self.assertEqual(events[0]["agentRunId"], "ar_python_smoke")
        self.assertIn("Explain closures.", events[2]["text"])
        self.assertEqual(events[1]["label"], "graph:python-smoke")
        self.assertEqual(events[3]["label"], "graph:python-smoke")

    def test_worker_omits_usage_snapshot_when_no_model_usage_was_observed(
        self,
    ) -> None:
        # Given
        worker = AgentRunWorker()

        # When
        events = worker.handle_line(VALID_START_COMMAND)

        # Then
        self.assertNotIn("usage.snapshot", [event["type"] for event in events])

    def test_worker_emits_schema_valid_usage_snapshot_before_completed_run(
        self,
    ) -> None:
        # Given
        worker = AgentRunWorker()

        # When
        events = worker.handle_line(
            _start_command_for_graph("graph:python-smoke-usage")
        )

        # Then
        for event in events:
            EVENT_VALIDATOR.validate(event)
        self.assertEqual(
            [event["type"] for event in events],
            [
                "run.started",
                "progress.update",
                "message.delta",
                "progress.update",
                "usage.snapshot",
                "run.completed",
            ],
        )
        self.assertEqual(
            events[-2],
            {
                "version": 1,
                "type": "usage.snapshot",
                "usage": {
                    "inputTokens": 11,
                    "outputTokens": 7,
                    "totalTokens": 18,
                    "cachedInputTokens": 3,
                    "cacheCreationInputTokens": 2,
                    "reasoningOutputTokens": 1,
                },
                "modelUsage": [
                    {
                        "provider": "synthetic",
                        "model": "model:deterministic-smoke",
                        "graphId": "graph:python-smoke-usage",
                        "nodeName": "draft_response",
                        "inputTokens": 11,
                        "outputTokens": 7,
                        "totalTokens": 18,
                        "cachedInputTokens": 3,
                        "cacheCreationInputTokens": 2,
                        "reasoningOutputTokens": 1,
                    },
                ],
            },
        )

    def test_worker_emits_usage_snapshot_before_failed_run_when_usage_was_observed(
        self,
    ) -> None:
        # Given
        worker = AgentRunWorker()

        # When
        events = worker.handle_line(
            _start_command_for_graph("graph:python-smoke-usage-failure")
        )

        # Then
        for event in events:
            EVENT_VALIDATOR.validate(event)
        self.assertEqual(
            [event["type"] for event in events],
            [
                "run.started",
                "progress.update",
                "progress.update",
                "usage.snapshot",
                "run.failed",
            ],
        )
        self.assertEqual(events[-1]["errorClassification"], "internal")

    def test_worker_rejects_unsupported_graph_before_execution(self) -> None:
        # Given
        command = json.loads(VALID_START_COMMAND)
        command["behaviorVersion"]["graph"] = "graph:unknown"
        worker = AgentRunWorker()

        # When
        events = worker.handle_line(json.dumps(command) + "\n")

        # Then
        for event in events:
            EVENT_VALIDATOR.validate(event)
        self.assertEqual(
            [event["type"] for event in events],
            ["run.started", "progress.update", "progress.update", "run.failed"],
        )
        self.assertEqual(events[-1]["errorClassification"], "validation")

    def test_worker_telemetry_attributes_align_with_ts_agent_run_names(self) -> None:
        # Given
        command = json.loads(VALID_START_COMMAND)

        # When
        attributes = agent_run_attributes(command)

        # Then
        self.assertEqual(attributes[AGENT_RUN_ID_ATTRIBUTE], "ar_python_smoke")
        self.assertEqual(
            attributes[RUNTIME_PROFILE_ID_ATTRIBUTE], "runtime-development"
        )
        self.assertEqual(
            attributes[AGENT_BEHAVIOR_ATTRIBUTES["graph"]],
            "graph:python-smoke",
        )

    def test_graph_telemetry_constants_have_bounded_attribute_names(self) -> None:
        # Given / When / Then
        self.assertEqual(GRAPH_ID_ATTRIBUTE, "metadata.agent_graph.id")
        self.assertEqual(GRAPH_NODE_NAME_ATTRIBUTE, "graph.node.name")

    def test_agent_run_telemetry_marks_completed_runs_ok(self) -> None:
        # Given
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        # When
        with telemetry.start_run(json.loads(VALID_START_COMMAND)) as span:
            telemetry.finish_run(span, {"type": "run.completed"})

        # Then
        finished_span = exporter.get_finished_spans()[0]
        self.assertEqual(finished_span.status.status_code, StatusCode.OK)

    def test_agent_run_telemetry_marks_failed_runs_error(self) -> None:
        # Given
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        # When
        with telemetry.start_run(json.loads(VALID_START_COMMAND)) as span:
            telemetry.finish_run(
                span,
                {"type": "run.failed", "errorClassification": "validation"},
            )

        # Then
        finished_span = exporter.get_finished_spans()[0]
        self.assertEqual(finished_span.status.status_code, StatusCode.ERROR)

    def test_model_call_telemetry_records_genai_usage_and_graph_node_context(
        self,
    ) -> None:
        # Given
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        # When
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

        # Then
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
        model_span = next(
            span
            for span in exporter.get_finished_spans()
            if span.name == "gen_ai.inference.client"
        )
        attributes = model_span.attributes
        self.assertIsNotNone(attributes)
        assert attributes is not None
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
        # Given
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        # When
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

        # Then
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
        # Given
        exporter = InMemorySpanExporter()
        telemetry = AgentRunTelemetry(tracer_provider(exporter))

        # When
        with telemetry.start_run(json.loads(VALID_START_COMMAND)):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                with telemetry.start_model_call(
                    provider="synthetic",
                    model="model:failing",
                    usage=ProviderUsage(input_tokens=2, output_tokens=1),
                ):
                    raise RuntimeError("synthetic failure")
            snapshot = telemetry.usage_snapshot_event()

        # Then
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

    def test_worker_reports_validation_failure_before_graph_execution(self) -> None:
        # Given
        worker = AgentRunWorker()

        # When
        events = worker.handle_line(
            '{"version":1,"type":"run.start","agentRunId":""}\n'
        )

        # Then
        self.assertEqual(
            events,
            [{"version": 1, "type": "run.failed", "errorClassification": "validation"}],
        )

    def test_worker_confirms_cancel_command(self) -> None:
        # Given
        worker = AgentRunWorker()

        # When
        events = worker.handle_line(
            '{"version":1,"type":"run.cancel","agentRunId":"ar_python_smoke"}\n',
        )

        # Then
        self.assertEqual(events, [{"version": 1, "type": "run.cancelled"}])

    def test_run_worker_writes_ndjson_events(self) -> None:
        # Given
        output = StringIO()

        # When
        run_worker([VALID_START_COMMAND], output)
        events = _decode_events(output.getvalue())

        # Then
        self.assertEqual(events[0]["type"], "run.started")
        self.assertEqual(events[-1]["type"], "run.completed")


def tracer_provider(exporter: InMemorySpanExporter) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


if __name__ == "__main__":
    unittest.main()
