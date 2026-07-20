import json
import unittest
from io import StringIO

from agent_runtime_python.experiment import (
    DirectWorkerTarget,
    ExperimentConfig,
    JsonlResultRecorder,
    TsGatewayTarget,
    TargetRun,
    TrialPlanner,
    build_trial_plan,
    create_target,
    record_trial_result,
    run_experiment,
)
from agent_runtime_python.protocol import COMMAND_VALIDATOR


COMPLETE_BEHAVIOR_VERSION = {
    "graph": "graph:python-smoke",
    "state": "state:smoke-v1",
    "action": "action:reply-v1",
    "prompt": "prompt:closures-v1",
    "tool": "tool:none-v1",
    "model": "model:deterministic-smoke",
    "sourceRevision": "0123456789abcdef0123456789abcdef01234567",
}


class ExperimentTest(unittest.TestCase):
    def test_build_trial_plan_generates_protocol_compliant_parameter_sweep(self) -> None:
        # Given
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise", "detailed"], "temperature": [0, 1]},
        )

        # When
        trials = build_trial_plan(config)

        # Then
        self.assertEqual(len(trials), 4)
        self.assertEqual(
            [trial.parameters for trial in trials],
            [
                {"style": "concise", "temperature": 0},
                {"style": "concise", "temperature": 1},
                {"style": "detailed", "temperature": 0},
                {"style": "detailed", "temperature": 1},
            ],
        )
        for trial in trials:
            COMMAND_VALIDATOR.validate(trial.command)
            self.assertEqual(trial.command["type"], "run.start")
            self.assertEqual(trial.command["runtimeProfile"]["profileId"], "runtime-development")
            self.assertIn("trialParameter", trial.command["behaviorVersion"])
            self.assertIn("Trial parameters:", trial.command["input"]["message"])

    def test_published_trial_requires_complete_behavior_identity(self) -> None:
        # Given
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise"]},
            runtime_profile="published",
            behavior_version={"graph": "graph:python-smoke"},
        )

        # When / Then
        with self.assertRaisesRegex(
            ValueError,
            "complete behavior identity",
        ):
            build_trial_plan(config)

    def test_comparable_trial_requires_complete_behavior_identity(self) -> None:
        # Given
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise"]},
            comparable=True,
            behavior_version={"graph": "graph:python-smoke"},
        )

        # When / Then
        with self.assertRaisesRegex(
            ValueError,
            "complete behavior identity",
        ):
            build_trial_plan(config)

    def test_published_trial_accepts_complete_behavior_identity(self) -> None:
        # Given
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise"]},
            runtime_profile="published",
            behavior_version=COMPLETE_BEHAVIOR_VERSION,
        )

        # When
        trials = build_trial_plan(config)

        # Then
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0].command["runtimeProfile"]["profileId"], "runtime-published")
        COMMAND_VALIDATOR.validate(trials[0].command)

    def test_run_experiment_records_direct_worker_trial_results_as_jsonl(self) -> None:
        # Given
        output = StringIO()
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise"]},
        )

        # When
        results = run_experiment(
            config,
            target=DirectWorkerTarget(),
            recorder=JsonlResultRecorder(output),
        )

        # Then
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].outcome, "succeeded")
        self.assertIn("Explain closures.", results[0].response_summary)
        recorded = json.loads(output.getvalue())
        self.assertEqual(recorded["trialId"], results[0].trial_id)
        self.assertEqual(recorded["agentRunId"], results[0].agent_run_id)
        self.assertEqual(recorded["parameters"], {"style": "concise"})
        self.assertEqual(recorded["outcome"], "succeeded")
        self.assertEqual(recorded["terminalEvent"], "run.completed")
        self.assertEqual(recorded["requestedRuntimeProfileId"], "runtime-development")
        self.assertEqual(recorded["submittedRuntimeProfileId"], "runtime-development")
        self.assertEqual(
            recorded["requestedBehaviorVersion"],
            recorded["submittedBehaviorVersion"],
        )

    def test_record_trial_result_captures_failed_terminal_outcome(self) -> None:
        # Given
        trial = build_trial_plan(
            ExperimentConfig(
                message="Explain closures.",
                parameter_matrix={"style": ["concise"]},
            ),
        )[0]

        # When
        result = record_trial_result(
            trial,
            TargetRun(
                events=[{"version": 1, "type": "run.failed", "errorClassification": "validation"}],
                submitted_runtime_profile_id="runtime-development",
                submitted_behavior_version=trial.command["behaviorVersion"],
            ),
        )

        # Then
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.terminal_event, "run.failed")
        self.assertEqual(result.error_classification, "validation")

    def test_gateway_target_posts_message_and_decodes_ndjson_events(self) -> None:
        # Given
        captured_requests = []

        class FakeResponse:
            status = 200

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def __iter__(self):
                return iter(
                    [
                        b'{"version":1,"type":"run.started","agentRunId":"ar_gateway"}\n',
                        b'{"version":1,"type":"message.delta","text":"Gateway response."}\n',
                        b'{"version":1,"type":"run.completed"}\n',
                    ],
                )

        def open_agent_run(request):
            captured_requests.append(request)
            return FakeResponse()

        target = TsGatewayTarget("http://localhost:3000", open_agent_run=open_agent_run)
        trial = build_trial_plan(
            ExperimentConfig(
                message="Explain closures.",
                parameter_matrix={"style": ["concise"]},
            ),
        )[0]

        # When
        target_run = target.run(trial)

        # Then
        self.assertEqual(captured_requests[0].full_url, "http://localhost:3000/api/agent-runs")
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
        self.assertEqual(record_trial_result(trial, target_run).agent_run_id, "ar_gateway")

    def test_build_trial_plan_accepts_custom_planner_extension_point(self) -> None:
        # Given
        class FixedPlanner:
            def parameter_sets(self, _config: ExperimentConfig):
                return [{"candidate": "optuna-style"}]

        planner: TrialPlanner = FixedPlanner()

        # When
        trials = build_trial_plan(
            ExperimentConfig(
                message="Explain closures.",
                parameter_matrix={"ignored": ["matrix"]},
            ),
            planner=planner,
        )

        # Then
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0].parameters, {"candidate": "optuna-style"})

    def test_create_target_selects_gateway_target(self) -> None:
        # Given / When
        target = create_target("ts-gateway", "http://localhost:3000")

        # Then
        self.assertIsInstance(target, TsGatewayTarget)


if __name__ == "__main__":
    unittest.main()
