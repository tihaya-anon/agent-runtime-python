import json
import unittest
from io import StringIO

from agent_runtime_python import __version__
from agent_runtime_python.runtime.protocol import EVENT_VALIDATOR
from agent_runtime_python.runtime.worker import AgentRunWorker, main, run_worker

from tests.worker_helpers import (
    VALID_START_COMMAND,
    decode_events,
    start_command_for_graph,
)


class WorkerRuntimeTest(unittest.TestCase):
    def test_package_exposes_version(self) -> None:
        version = __version__

        self.assertTrue(bool(version))

    def test_worker_entrypoint_exits_successfully(self) -> None:
        output = StringIO()

        exit_code = main([], output)

        self.assertEqual(exit_code, 0)

    def test_worker_executes_smoke_graph_for_valid_start_command(self) -> None:
        worker = AgentRunWorker()

        events = worker.handle_line(VALID_START_COMMAND)

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
        worker = AgentRunWorker()

        events = worker.handle_line(VALID_START_COMMAND)

        self.assertNotIn("usage.snapshot", [event["type"] for event in events])

    def test_worker_emits_schema_valid_usage_snapshot_before_completed_run(
        self,
    ) -> None:
        worker = AgentRunWorker()

        events = worker.handle_line(start_command_for_graph("graph:python-smoke-usage"))

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
        worker = AgentRunWorker()

        events = worker.handle_line(
            start_command_for_graph("graph:python-smoke-usage-failure")
        )

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
        command = json.loads(VALID_START_COMMAND)
        command["behaviorVersion"]["graph"] = "graph:unknown"
        worker = AgentRunWorker()

        events = worker.handle_line(json.dumps(command) + "\n")

        for event in events:
            EVENT_VALIDATOR.validate(event)
        self.assertEqual(
            [event["type"] for event in events],
            ["run.started", "progress.update", "progress.update", "run.failed"],
        )
        self.assertEqual(events[-1]["errorClassification"], "validation")

    def test_worker_reports_validation_failure_before_graph_execution(self) -> None:
        worker = AgentRunWorker()

        events = worker.handle_line(
            '{"version":1,"type":"run.start","agentRunId":""}\n'
        )

        self.assertEqual(
            events,
            [{"version": 1, "type": "run.failed", "errorClassification": "validation"}],
        )

    def test_worker_confirms_cancel_command(self) -> None:
        worker = AgentRunWorker()

        events = worker.handle_line(
            '{"version":1,"type":"run.cancel","agentRunId":"ar_python_smoke"}\n',
        )

        self.assertEqual(events, [{"version": 1, "type": "run.cancelled"}])

    def test_run_worker_writes_ndjson_events(self) -> None:
        output = StringIO()

        run_worker([VALID_START_COMMAND], output)
        events = decode_events(output.getvalue())

        self.assertEqual(events[0]["type"], "run.started")
        self.assertEqual(events[-1]["type"], "run.completed")


if __name__ == "__main__":
    unittest.main()
