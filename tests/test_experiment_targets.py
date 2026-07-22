import json
import unittest

from agent_runtime_python.experiment import (
    ExperimentConfig,
    InternalHttpStreamingTarget,
    TsGatewayTarget,
    build_trial_plan,
    create_target,
    record_trial_result,
)


class FakeResponse:
    status = 200

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def __iter__(self):
        return iter(self._lines)


class ExperimentTargetTest(unittest.TestCase):
    def test_gateway_target_posts_message_and_decodes_ndjson_events(self) -> None:
        captured_requests = []

        def open_agent_run(request):
            captured_requests.append(request)
            return FakeResponse(
                [
                    b'{"version":1,"type":"run.started","agentRunId":"ar_gateway"}\n',
                    b'{"version":1,"type":"message.delta","text":"Gateway response."}\n',
                    b'{"version":1,"type":"run.completed"}\n',
                ],
            )

        target = TsGatewayTarget("http://localhost:3000", open_agent_run=open_agent_run)
        trial = build_trial_plan(
            ExperimentConfig(
                message="Explain closures.",
                parameter_matrix={"style": ["concise"]},
            ),
        )[0]

        target_run = target.run(trial)

        self.assertEqual(
            captured_requests[0].full_url, "http://localhost:3000/api/agent-runs"
        )
        self.assertEqual(
            json.loads(captured_requests[0].data),
            {"message": trial.command["input"]["message"]},
        )
        self.assertEqual(
            [event["type"] for event in target_run.events],
            ["run.started", "message.delta", "run.completed"],
        )
        self.assertIsNone(target_run.submitted_runtime_profile_id)
        self.assertIsNone(target_run.submitted_behavior_version)
        self.assertEqual(
            record_trial_result(trial, target_run).agent_run_id, "ar_gateway"
        )

    def test_internal_http_target_posts_worker_command_and_decodes_ndjson_events(
        self,
    ) -> None:
        captured_requests = []

        def open_agent_run(request):
            captured_requests.append(request)
            return FakeResponse(
                [
                    b'{"version":1,"type":"run.started","agentRunId":"ar_http"}\n',
                    b'{"version":1,"type":"message.delta","text":"HTTP response."}\n',
                    b'{"version":1,"type":"run.completed"}\n',
                ],
            )

        target = InternalHttpStreamingTarget(
            "http://runtime.internal",
            open_agent_run=open_agent_run,
        )
        trial = build_trial_plan(
            ExperimentConfig(
                message="Explain closures.",
                parameter_matrix={"style": ["concise"]},
            ),
        )[0]

        target_run = target.run(trial)

        self.assertEqual(
            captured_requests[0].full_url,
            "http://runtime.internal/internal/agent-runs",
        )
        self.assertEqual(json.loads(captured_requests[0].data), trial.command)
        self.assertEqual(captured_requests[0].headers["Accept"], "application/x-ndjson")
        self.assertEqual(
            [event["type"] for event in target_run.events],
            ["run.started", "message.delta", "run.completed"],
        )
        self.assertEqual(target_run.submitted_runtime_profile_id, "runtime-development")
        self.assertEqual(
            target_run.submitted_behavior_version,
            trial.command["behaviorVersion"],
        )

    def test_create_target_selects_gateway_target(self) -> None:
        target = create_target("ts-gateway", "http://localhost:3000")

        self.assertIsInstance(target, TsGatewayTarget)

    def test_create_target_selects_internal_http_target(self) -> None:
        target = create_target("internal-http", "http://runtime.internal")

        self.assertIsInstance(target, InternalHttpStreamingTarget)


if __name__ == "__main__":
    unittest.main()
