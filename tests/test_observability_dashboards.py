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


def _panel_by_title(dashboard: dict, title: str) -> dict:
    for panel in dashboard["panels"]:
        if panel["title"] == title:
            return panel
    raise AssertionError(f"Missing dashboard panel: {title}")


def _field_link(panel: dict, field_name: str) -> dict:
    overrides = panel["fieldConfig"]["overrides"]
    override = next(
        (
            candidate
            for candidate in overrides
            if candidate["matcher"]["options"] == field_name
        ),
        None,
    )
    if override is None:
        raise AssertionError(f"Missing field override: {field_name}")

    link_property = next(
        (
            property_value
            for property_value in override["properties"]
            if property_value["id"] == "links"
            and isinstance(property_value["value"], list)
        ),
        None,
    )
    if link_property is None:
        raise AssertionError(f"Missing field link: {field_name}")

    return link_property["value"][0]


def _default_field_link(panel: dict) -> dict:
    links = panel["fieldConfig"]["defaults"]["links"]
    if not links:
        raise AssertionError(f"Missing default field link: {panel['title']}")
    return links[0]


class ObservabilityDashboardTest(unittest.TestCase):
    def test_agent_runtime_experiment_dashboard_json_matches_generator(self) -> None:
        # Given
        generator = _load_dashboard_module()

        # When
        expected = generator.build_dashboard()
        actual = json.loads(DASHBOARD_JSON_PATH.read_text(encoding="utf-8"))

        # Then
        self.assertEqual(actual, expected)

    def test_agent_runtime_experiment_dashboard_has_visual_summary_panels(self) -> None:
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
        target_queries = [
            target.get("query", "")
            for panel in dashboard["panels"]
            for target in panel.get("targets", [])
        ]
        panel_types = [panel["type"] for panel in dashboard["panels"]]

        # Then
        self.assertEqual(dashboard["uid"], "agent-runtime-experiments")
        self.assertEqual(
            panel_titles,
            {
                "Trials / min",
                "Failed Runs / min",
                "Agent Run p95",
                "Trial Error %",
                "Trial Outcome Mix",
                "Runtime Activity Mix",
                "Agent Run Latency Distribution",
                "Trial Starts / min",
                "Duration p95",
                "Provider Tokens by Model",
                "Provider Tokens by Graph Node",
                "Provider Cache Tokens",
                "Model Call Latency p95",
                "Recent Trial Drilldown",
            },
        )
        self.assertEqual(panel_types.count("table"), 1)
        self.assertIn("stat", panel_types)
        self.assertIn("gauge", panel_types)
        self.assertIn("piechart", panel_types)
        self.assertIn("barchart", panel_types)
        self.assertIn("bargauge", panel_types)
        self.assertIn("heatmap", panel_types)
        self.assertIn("timeseries", panel_types)
        self.assertEqual(
            variable_names,
            {"study_id", "trial_id", "trial_outcome", "agent_run_id"},
        )
        self.assertIn("metadata.experiment.study_id", queries)
        self.assertIn("metadata.experiment.trial_id", queries)
        self.assertIn("metadata.experiment.outcome", queries)
        self.assertIn("$trial_outcome", queries)
        self.assertIn("traces_spanmetrics_calls_total", queries)
        self.assertIn("STATUS_CODE_ERROR", queries)
        self.assertIn("succeeded", queries)
        self.assertIn("failed", queries)
        self.assertNotIn("loki", queries)
        self.assertNotIn("graph_id", queries)
        self.assertTrue(any("trace:id" in query for query in target_queries))

    def test_agent_runtime_experiment_dashboard_has_provider_usage_panels(self) -> None:
        # Given
        dashboard = json.loads(DASHBOARD_JSON_PATH.read_text(encoding="utf-8"))

        # When
        panel_titles = {panel["title"] for panel in dashboard["panels"]}
        queries = json.dumps(dashboard["panels"])
        target_queries = [
            target.get("query", "")
            for panel in dashboard["panels"]
            for target in panel.get("targets", [])
        ]
        target_exprs = [
            target.get("expr", "")
            for panel in dashboard["panels"]
            for target in panel.get("targets", [])
        ]

        # Then
        self.assertLessEqual(
            {
                "Provider Tokens by Model",
                "Provider Tokens by Graph Node",
                "Provider Cache Tokens",
                "Model Call Latency p95",
                "Recent Trial Drilldown",
            },
            panel_titles,
        )
        for attribute_name in [
            "gen_ai.inference.client",
            "metadata.experiment.study_id",
            "gen_ai.system",
            "gen_ai.request.model",
            "metadata.agent_graph.id",
            "graph.node.name",
            "gen_ai.usage.total_tokens",
            "gen_ai.usage.cache_read.input_tokens",
            "gen_ai.usage.cache_creation.input_tokens",
            "usage.inputTokens",
            "usage.outputTokens",
            "usage.totalTokens",
            "usage.cachedInputTokens",
            "usage.cacheCreationInputTokens",
            "usage.reasoningOutputTokens",
            "modelUsage",
        ]:
            self.assertIn(attribute_name, queries)
        self.assertTrue(
            any(
                "select(" in query
                and "gen_ai.usage.total_tokens" in query
                and "gen_ai.request.model" in query
                for query in target_queries
            )
        )
        self.assertTrue(
            any(
                "histogram_quantile(0.95" in expr
                and 'span_name="gen_ai.inference.client"' in expr
                for expr in target_exprs
            )
        )
        for title in [
            "Provider Tokens by Model",
            "Provider Tokens by Graph Node",
            "Provider Cache Tokens",
        ]:
            panel = _panel_by_title(dashboard, title)
            self.assertEqual(panel["type"], "barchart")
            self.assertEqual(panel["options"]["orientation"], "horizontal")
            self.assertEqual(panel["options"]["showValue"], "always")
            self.assertEqual(panel["options"]["stacking"], "normal")
            transformations = json.dumps(panel["transformations"])
            self.assertIn("filterFieldsByName", transformations)
            self.assertNotIn("gen_ai.usage.total_tokens", transformations)
        self.assertEqual(
            _panel_by_title(dashboard, "Model Call Latency p95")["type"],
            "stat",
        )
        self.assertEqual(
            _panel_by_title(dashboard, "Recent Trial Drilldown")["type"],
            "table",
        )
        out_of_scope_surface = " ".join(
            [
                *(title.lower() for title in panel_titles),
                *(query.lower() for query in target_queries),
            ]
        )
        for forbidden in ["budget", "cost", "tool", "retrieval", "evaluator"]:
            self.assertNotIn(forbidden, out_of_scope_surface)

    def test_agent_runtime_experiment_dashboard_links_trace_and_span_ids(self) -> None:
        # Given
        dashboard = json.loads(DASHBOARD_JSON_PATH.read_text(encoding="utf-8"))

        # When
        drilldown = _panel_by_title(dashboard, "Recent Trial Drilldown")
        trace_link = _field_link(drilldown, "traceID")
        span_link = _field_link(drilldown, "spanID")

        # Then
        self.assertIn("${__value.raw}", trace_link["url"])
        self.assertIn("${__data.fields.traceIdHidden}", span_link["url"])
        self.assertIn("${__value.raw}", span_link["url"])
        for link in [trace_link, span_link]:
            self.assertEqual(link["title"], "${__value.raw} ↗")
            self.assertTrue(link["targetBlank"])
            self.assertIn("${__from}", link["url"])
            self.assertIn("${__to}", link["url"])
            self.assertIn("/explore?schemaVersion=1&panes=", link["url"])

    def test_trial_outcome_mix_filters_the_drilldown_table(self) -> None:
        # Given
        dashboard = json.loads(DASHBOARD_JSON_PATH.read_text(encoding="utf-8"))

        # When
        outcome_mix = _panel_by_title(dashboard, "Trial Outcome Mix")
        outcome_link = _default_field_link(outcome_mix)

        # Then
        self.assertEqual(outcome_link["title"], "${__field.labels.outcome} trials")
        self.assertFalse(outcome_link["targetBlank"])
        self.assertIn(
            "var-trial_outcome=${__field.labels.outcome}", outcome_link["url"]
        )
        self.assertIn("var-study_id=$study_id", outcome_link["url"])
        self.assertIn("var-trial_id=", outcome_link["url"])
        self.assertIn("var-agent_run_id=", outcome_link["url"])


if __name__ == "__main__":
    unittest.main()
