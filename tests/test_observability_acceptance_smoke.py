import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_MODULE_PATH = (
    ROOT / "ops" / "observability" / "acceptance" / "run_observability_smoke.py"
)
PROVIDER_USAGE_ACCEPTANCE_MODULE_PATH = (
    ROOT / "ops" / "observability" / "acceptance" / "run_provider_usage_acceptance.py"
)


def _load_acceptance_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_observability_smoke",
        ACCEPTANCE_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load observability acceptance module")

    module = importlib.util.module_from_spec(spec)
    sys.modules["run_observability_smoke"] = module
    spec.loader.exec_module(module)
    return module


def _load_provider_usage_acceptance_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_provider_usage_acceptance",
        PROVIDER_USAGE_ACCEPTANCE_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load provider usage acceptance module")

    module = importlib.util.module_from_spec(spec)
    sys.modules["run_provider_usage_acceptance"] = module
    spec.loader.exec_module(module)
    return module


class ObservabilityAcceptanceSmokeTest(unittest.TestCase):
    def test_compose_up_command_uses_repo_observability_compose_file(self) -> None:
        # Given
        acceptance = _load_acceptance_module()
        compose_file = ROOT / "compose.observability.yaml"

        # When
        command = acceptance.compose_up_command(compose_file)

        # Then
        self.assertEqual(
            command,
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "up",
                "-d",
                "--build",
            ],
        )

    def test_experiment_command_targets_internal_http_runtime(self) -> None:
        # Given
        acceptance = _load_acceptance_module()
        output_path = Path("/tmp/results.jsonl")

        # When
        command = acceptance.experiment_command(
            python_executable="/venv/bin/python",
            runtime_url="http://127.0.0.1:8088",
            results_path=output_path,
            study_id="observability-smoke-test",
            params=["promptStyle=concise,detailed"],
        )

        # Then
        self.assertIn("-m", command)
        self.assertIn("agent_runtime_python.experiment", command)
        self.assertIn("--target", command)
        self.assertIn("internal-http", command)
        self.assertIn("--study-id", command)
        self.assertIn("observability-smoke-test", command)
        self.assertIn("--output", command)
        self.assertIn(str(output_path), command)
        self.assertIn("promptStyle=concise,detailed", command)

    def test_experiment_command_can_request_failed_runtime_run(self) -> None:
        # Given
        acceptance = _load_acceptance_module()

        # When
        command = acceptance.experiment_command(
            python_executable="/venv/bin/python",
            runtime_url="http://127.0.0.1:8088",
            results_path=Path("/tmp/failed.jsonl"),
            study_id="observability-smoke-test-failure",
            params=["scenario=unsupportedGraph"],
            behavior_versions=["graph=graph:observability-smoke-unsupported"],
        )

        # Then
        self.assertIn("--behavior-version", command)
        self.assertIn("graph=graph:observability-smoke-unsupported", command)
        self.assertIn("scenario=unsupportedGraph", command)

    def test_read_trial_identities_returns_dashboard_values(self) -> None:
        # Given
        acceptance = _load_acceptance_module()
        results_path = Path("/tmp/test-agent-runtime-observability-results.jsonl")
        results_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "trialId": "study-trial-0001",
                            "agentRunId": "ar_study_trial_0001",
                        }
                    ),
                    json.dumps(
                        {
                            "trialId": "study-trial-0002",
                            "agentRunId": "ar_study_trial_0002",
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        # When
        identities = acceptance.read_trial_identities(results_path, "study")

        # Then
        self.assertEqual(
            identities,
            [
                acceptance.TrialIdentity(
                    study_id="study",
                    trial_id="study-trial-0001",
                    agent_run_id="ar_study_trial_0001",
                ),
                acceptance.TrialIdentity(
                    study_id="study",
                    trial_id="study-trial-0002",
                    agent_run_id="ar_study_trial_0002",
                ),
            ],
        )

    def test_provider_usage_acceptance_requires_usage_jsonl_record(self) -> None:
        # Given
        acceptance = _load_provider_usage_acceptance_module()
        results_path = Path("/tmp/test-agent-runtime-provider-usage-results.jsonl")
        results_path.write_text(
            json.dumps(
                {
                    "trialId": "study-trial-0001",
                    "agentRunId": "ar_study_trial_0001",
                    "usage": acceptance.EXPECTED_USAGE,
                    "modelUsage": [acceptance.EXPECTED_MODEL_USAGE],
                }
            ),
            encoding="utf-8",
        )

        # When
        record = acceptance.read_single_result(results_path)

        # Then
        acceptance.require_usage_record(record, results_path)

    def test_provider_usage_acceptance_rejects_missing_usage_jsonl_record(
        self,
    ) -> None:
        # Given
        acceptance = _load_provider_usage_acceptance_module()

        # When / Then
        with self.assertRaises(acceptance.ObservabilitySmokeError):
            acceptance.require_usage_record({}, Path("/tmp/missing-usage.jsonl"))

    def test_provider_usage_acceptance_command_requests_usage_graph(self) -> None:
        # Given
        acceptance = _load_provider_usage_acceptance_module()

        # When
        command = acceptance.experiment_command(
            python_executable="/venv/bin/python",
            runtime_url="http://127.0.0.1:8088",
            results_path=Path("/tmp/provider-usage.jsonl"),
            study_id="provider-usage-test",
            params=["promptStyle=concise"],
            behavior_versions=[f"graph={acceptance.USAGE_GRAPH_ID}"],
        )

        # Then
        self.assertIn("--behavior-version", command)
        self.assertIn("graph=graph:python-smoke-usage", command)
        self.assertIn("promptStyle=concise", command)


if __name__ == "__main__":
    unittest.main()
