import json
import unittest

from fastapi.testclient import TestClient

from agent_runtime_python.api.app import NDJSON_CONTENT_TYPE, create_app
from agent_runtime_python.runtime.protocol import EVENT_VALIDATOR

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


def _decode_events(body: bytes) -> list[dict[str, object]]:
    events = [json.loads(line) for line in body.decode("utf-8").splitlines()]
    for event in events:
        EVENT_VALIDATOR.validate(event)

    return events


class InternalApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_internal_agent_runs_endpoint_streams_worker_events(self) -> None:
        # Given / When
        response = self.client.post(
            "/internal/agent-runs",
            content=VALID_START_COMMAND,
        )

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], NDJSON_CONTENT_TYPE)
        events = _decode_events(response.content)
        self.assertEqual(events[0]["type"], "run.started")
        self.assertEqual(events[-1]["type"], "run.completed")

    def test_internal_cancel_endpoint_returns_worker_cancel_event(self) -> None:
        # Given / When
        response = self.client.post("/internal/agent-runs/ar_python_smoke/cancel")

        # Then
        self.assertEqual(response.status_code, 200)
        events = _decode_events(response.content)
        self.assertEqual(events, [{"version": 1, "type": "run.cancelled"}])

    def test_internal_health_endpoint_reports_ok(self) -> None:
        # Given / When
        response = self.client.get("/healthz")

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_internal_api_rejects_unknown_route(self) -> None:
        # Given / When
        response = self.client.post("/internal/unknown")

        # Then
        self.assertEqual(response.status_code, 404)

    def test_request_logging_middleware_includes_agent_run_id(self) -> None:
        # Given / When / Then
        with self.assertLogs(level="INFO") as logs:
            self.client.post("/internal/agent-runs", content=VALID_START_COMMAND)

        self.assertTrue(
            any('"agent_run_id":"ar_python_smoke"' in entry for entry in logs.output)
        )


if __name__ == "__main__":
    unittest.main()
