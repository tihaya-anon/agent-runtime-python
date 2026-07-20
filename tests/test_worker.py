import json
import unittest
from io import StringIO
from typing import Any

from agent_runtime_python import __version__
from agent_runtime_python.protocol import EVENT_VALIDATOR
from agent_runtime_python.telemetry import (
    AGENT_BEHAVIOR_ATTRIBUTES,
    AGENT_RUN_ID_ATTRIBUTE,
    RUNTIME_PROFILE_ID_ATTRIBUTE,
    agent_run_attributes,
)
from agent_runtime_python.worker import AgentRunWorker, main, run_worker

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

    def test_worker_telemetry_attributes_align_with_ts_agent_run_names(self) -> None:
        # Given
        command = json.loads(VALID_START_COMMAND)

        # When
        attributes = agent_run_attributes(command)

        # Then
        self.assertEqual(attributes[AGENT_RUN_ID_ATTRIBUTE], "ar_python_smoke")
        self.assertEqual(attributes[RUNTIME_PROFILE_ID_ATTRIBUTE], "runtime-development")
        self.assertEqual(
            attributes[AGENT_BEHAVIOR_ATTRIBUTES["graph"]],
            "graph:python-smoke",
        )

    def test_worker_reports_validation_failure_before_graph_execution(self) -> None:
        # Given
        worker = AgentRunWorker()

        # When
        events = worker.handle_line('{"version":1,"type":"run.start","agentRunId":""}\n')

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


if __name__ == "__main__":
    unittest.main()
