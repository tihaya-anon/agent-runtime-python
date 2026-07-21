import json
import unittest

from agent_runtime_python.internal_api import (
    NDJSON_CONTENT_TYPE,
    handle_internal_request,
)
from agent_runtime_python.protocol import EVENT_VALIDATOR

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
    def test_internal_agent_runs_endpoint_streams_worker_events(self) -> None:
        # Given / When
        response = handle_internal_request(
            "POST",
            "/internal/agent-runs",
            VALID_START_COMMAND.encode("utf-8"),
        )

        # Then
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, NDJSON_CONTENT_TYPE)
        events = _decode_events(response.body)
        self.assertEqual(events[0]["type"], "run.started")
        self.assertEqual(events[-1]["type"], "run.completed")

    def test_internal_cancel_endpoint_returns_worker_cancel_event(self) -> None:
        # Given / When
        response = handle_internal_request(
            "POST",
            "/internal/agent-runs/ar_python_smoke/cancel",
            b"",
        )

        # Then
        self.assertEqual(response.status, 200)
        events = _decode_events(response.body)
        self.assertEqual(events, [{"version": 1, "type": "run.cancelled"}])

    def test_internal_api_rejects_unknown_route(self) -> None:
        # Given / When
        response = handle_internal_request("POST", "/internal/unknown", b"")

        # Then
        self.assertEqual(response.status, 404)
        self.assertEqual(json.loads(response.body), {"error": "not_found"})


if __name__ == "__main__":
    unittest.main()
