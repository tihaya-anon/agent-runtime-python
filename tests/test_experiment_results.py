import json
import unittest
from io import StringIO

from agent_runtime_python.experiment import (
    DirectWorkerTarget,
    ExperimentConfig,
    JsonlResultRecorder,
    TargetRun,
    build_trial_plan,
    record_trial_result,
    run_experiment,
)


class ExperimentResultsTest(unittest.TestCase):
    def test_run_experiment_records_direct_worker_trial_results_as_jsonl(self) -> None:
        output = StringIO()
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise"]},
        )

        results = run_experiment(
            config,
            target=DirectWorkerTarget(),
            recorder=JsonlResultRecorder(output),
        )

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
        self.assertNotIn("usage", recorded)
        self.assertNotIn("modelUsage", recorded)

    def test_run_experiment_copies_final_usage_snapshot_to_jsonl(self) -> None:
        output = StringIO()
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise"]},
            behavior_version={"graph": "graph:python-smoke-usage"},
        )

        results = run_experiment(
            config,
            target=DirectWorkerTarget(),
            recorder=JsonlResultRecorder(output),
        )

        self.assertEqual(results[0].outcome, "succeeded")
        recorded = json.loads(output.getvalue())
        self.assertEqual(
            recorded["usage"],
            {
                "inputTokens": 11,
                "outputTokens": 7,
                "totalTokens": 18,
                "cachedInputTokens": 3,
                "cacheCreationInputTokens": 2,
                "reasoningOutputTokens": 1,
            },
        )
        self.assertEqual(
            recorded["modelUsage"],
            [
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
        )

    def test_record_trial_result_captures_failed_terminal_outcome(self) -> None:
        trial = build_trial_plan(
            ExperimentConfig(
                message="Explain closures.",
                parameter_matrix={"style": ["concise"]},
            ),
        )[0]

        result = record_trial_result(
            trial,
            TargetRun(
                events=[
                    {
                        "version": 1,
                        "type": "run.failed",
                        "errorClassification": "validation",
                    }
                ],
                submitted_runtime_profile_id="runtime-development",
                submitted_behavior_version=trial.command["behaviorVersion"],
            ),
        )

        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.terminal_event, "run.failed")
        self.assertEqual(result.error_classification, "validation")


if __name__ == "__main__":
    unittest.main()
