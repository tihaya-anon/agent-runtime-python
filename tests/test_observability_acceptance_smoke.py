import importlib.util
import json
import sys
import tomllib
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
PYPROJECT_PATH = ROOT / "pyproject.toml"


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

    def test_compose_exec_command_runs_inside_runtime_container(self) -> None:
        # Given
        acceptance = _load_acceptance_module()
        compose_file = ROOT / "compose.observability.yaml"

        # When
        command = acceptance.compose_exec_command(
            compose_file,
            "agent-runtime-python",
            ["python", "-m", "agent_runtime_python.experiment"],
        )

        # Then
        self.assertEqual(
            command,
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "exec",
                "-T",
                "agent-runtime-python",
                "python",
                "-m",
                "agent_runtime_python.experiment",
            ],
        )

    def test_compose_cp_command_copies_container_result_to_host(self) -> None:
        # Given
        acceptance = _load_acceptance_module()
        compose_file = ROOT / "compose.observability.yaml"

        # When
        command = acceptance.compose_cp_command(
            compose_file,
            "agent-runtime-python",
            Path("/tmp/provider-usage.jsonl"),
            Path("/tmp/provider-usage.jsonl"),
        )

        # Then
        self.assertEqual(
            command,
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "cp",
                "agent-runtime-python:/tmp/provider-usage.jsonl",
                "/tmp/provider-usage.jsonl",
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

    def test_provider_usage_acceptance_runs_experiment_in_container(self) -> None:
        # Given
        acceptance = _load_provider_usage_acceptance_module()
        args = acceptance.parse_args(
            [
                "--compose-file",
                str(ROOT / "compose.observability.yaml"),
                "--results-path",
                "/tmp/readable-provider-usage.jsonl",
            ]
        )

        # When
        container_path = acceptance.container_result_path(args)
        command = acceptance.compose_exec_command(
            args.compose_file,
            args.container_service,
            acceptance.experiment_command(
                python_executable="python",
                runtime_url=args.runtime_url,
                results_path=container_path,
                study_id="provider-usage-smoke-test",
                params=["promptStyle=concise"],
                behavior_versions=[f"graph={acceptance.USAGE_GRAPH_ID}"],
                message="Provider usage smoke run.",
            ),
        )

        # Then
        self.assertIn("exec", command)
        self.assertIn("-T", command)
        self.assertIn("agent-runtime-python", command)
        self.assertIn("python", command)
        self.assertIn("/tmp/readable-provider-usage.jsonl", command)
        self.assertIn("provider-usage-smoke-test", command)
        self.assertIn("Provider usage smoke run.", command)

    def test_pyproject_exposes_provider_usage_smoke_script(self) -> None:
        # Given
        pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))

        # When
        scripts = pyproject["project"]["scripts"]

        # Then
        self.assertEqual(
            scripts["agent-runtime-python-provider-usage-smoke"],
            "agent_runtime_python.observability.provider_usage_smoke:main",
        )


if __name__ == "__main__":
    unittest.main()
