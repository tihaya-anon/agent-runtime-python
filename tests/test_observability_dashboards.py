import importlib.util
import json
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_MODULE_PATH = (
    ROOT
    / "ops"
    / "observability"
    / "dashboards"
    / "generate_agent_runtime_experiments_dashboard.py"
)
DASHBOARD_JSON_PATH = (
    ROOT
    / "ops"
    / "observability"
    / "dashboards"
    / "agent-runtime-experiments.dashboard.json"
)


def _load_dashboard_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_agent_runtime_experiments_dashboard",
        DASHBOARD_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load dashboard generator module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ObservabilityDashboardTest(unittest.TestCase):
    def test_agent_runtime_experiment_dashboard_json_matches_generator(self) -> None:
        # Given
        generator = _load_dashboard_module()

        # When
        expected = generator.build_dashboard()
        actual = json.loads(DASHBOARD_JSON_PATH.read_text(encoding="utf-8"))

        # Then
        self.assertEqual(actual, expected)

    def test_agent_runtime_experiment_dashboard_has_detailed_panels(self) -> None:
        # Given
        dashboard = json.loads(DASHBOARD_JSON_PATH.read_text(encoding="utf-8"))

        # When
        panel_titles = {panel["title"] for panel in dashboard["panels"]}
        variable_names = {
            variable["name"] for variable in dashboard["templating"]["list"]
        }
        queries = json.dumps(dashboard["panels"])
        target_exprs = [
            target.get("expr", "")
            for panel in dashboard["panels"]
            for target in panel.get("targets", [])
        ]

        # Then
        self.assertEqual(dashboard["uid"], "agent-runtime-experiments")
        self.assertEqual(
            panel_titles,
            {
                "Recent Experiment Trials",
                "Trial Starts by Outcome",
                "Agent Run Duration p95",
                "Selected Trial Trace",
                "Graph and Node Breakdown",
                "Failed Runtime Runs",
                "Correlated Runtime Logs",
            },
        )
        self.assertEqual(
            variable_names,
            {"study_id", "trial_id", "graph_id", "agent_run_id"},
        )
        self.assertIn("metadata.experiment.study_id", queries)
        self.assertIn("metadata.experiment.trial_id", queries)
        self.assertIn("metadata.agent_graph.id", queries)
        self.assertIn("graph.node.name", queries)
        self.assertIn("traces_spanmetrics_calls_total", queries)
        self.assertIn(
            '{service_name="agent-runtime-python"} | json | __error__="" | '
            'agent_run_id="$agent_run_id"',
            target_exprs,
        )


if __name__ == "__main__":
    unittest.main()
