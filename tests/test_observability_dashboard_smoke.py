import copy
import importlib.util
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SMOKE_MODULE_PATH = ROOT / "ops" / "observability" / "acceptance" / "smoke_dashboard.py"
DASHBOARD_JSON_PATH = (
    ROOT
    / "ops"
    / "observability"
    / "dashboards"
    / "agent-runtime-experiments.dashboard.json"
)


def _load_smoke_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "smoke_dashboard",
        SMOKE_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load dashboard smoke module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ObservabilityDashboardSmokeTest(unittest.TestCase):
    def test_dashboard_contract_ignores_grafana_runtime_metadata(self) -> None:
        # Given
        smoke = _load_smoke_module()
        expected = smoke.load_json(DASHBOARD_JSON_PATH)
        actual = copy.deepcopy(expected)
        actual["id"] = 12
        actual["version"] = 4
        actual["panels"][0]["pluginVersion"] = "13.0.2"

        # Then
        smoke.compare_dashboard_contract(expected, actual)

    def test_dashboard_contract_detects_query_drift(self) -> None:
        # Given
        smoke = _load_smoke_module()
        expected = smoke.load_json(DASHBOARD_JSON_PATH)
        actual = copy.deepcopy(expected)
        actual["panels"][0]["targets"][0]["query"] = "{ true }"

        # Then
        with self.assertRaises(smoke.SmokeCheckError):
            smoke.compare_dashboard_contract(expected, actual)

    def test_dashboard_contract_requires_templating_variables(self) -> None:
        # Given
        smoke = _load_smoke_module()
        expected = smoke.load_json(DASHBOARD_JSON_PATH)
        actual = copy.deepcopy(expected)
        actual.pop("templating")

        # Then
        with self.assertRaises(smoke.SmokeCheckError):
            smoke.compare_dashboard_contract(expected, actual)


if __name__ == "__main__":
    unittest.main()
