#!/usr/bin/env python3
"""Smoke-check the Git-synced Agent Runtime Experiments dashboard in Grafana."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DASHBOARD_PATH = (
    ROOT
    / "ops"
    / "observability"
    / "dashboards"
    / "agent-runtime-experiments.dashboard.json"
)
DEFAULT_GRAFANA_URL = "http://127.0.0.1:3000"
DEFAULT_DASHBOARD_UID = "agent-runtime-experiments"
REQUIRED_DATASOURCES = {
    "prometheus": "prometheus",
    "tempo": "tempo",
    "loki": "loki",
}


class SmokeCheckError(RuntimeError):
    """Raised when the dashboard smoke check fails."""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    client = GrafanaClient(
        base_url=args.grafana_url,
        username=args.grafana_user,
        password=args.grafana_password,
    )
    expected_dashboard = load_json(args.dashboard_path)

    health = client.get_json("/api/health")
    database = health.get("database")
    if database not in {None, "ok"}:
        raise SmokeCheckError(f"Grafana health database status is {database!r}")
    print("Grafana health: ok")

    for uid, expected_type in REQUIRED_DATASOURCES.items():
        datasource = client.get_json(f"/api/datasources/uid/{quote(uid)}")
        actual_type = datasource.get("type")
        if actual_type != expected_type:
            raise SmokeCheckError(
                f"Datasource {uid!r} has type {actual_type!r}; expected {expected_type!r}"
            )
        print(f"Datasource {uid}: ok")

    response = client.get_json(f"/api/dashboards/uid/{quote(args.dashboard_uid)}")
    loaded_dashboard = response.get("dashboard")
    if not isinstance(loaded_dashboard, dict):
        raise SmokeCheckError(
            f"Dashboard {args.dashboard_uid!r} response is missing dashboard JSON"
        )

    compare_dashboard_contract(expected_dashboard, loaded_dashboard)

    meta = response.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    folder_title = meta.get("folderTitle")
    if (
        args.expected_folder_title is not None
        and folder_title != args.expected_folder_title
    ):
        raise SmokeCheckError(
            f"Dashboard folder is {folder_title!r}; expected {args.expected_folder_title!r}"
        )

    dashboard_url = meta.get("url") or f"/d/{args.dashboard_uid}"
    print(f"Dashboard {args.dashboard_uid}: ok at {dashboard_url}")
    if folder_title:
        print(f"Dashboard folder: {folder_title}")
    print("Dashboard smoke test passed.")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that PGL Grafana loaded the Agent Runtime Experiments dashboard."
    )
    parser.add_argument(
        "--grafana-url",
        default=os.environ.get("GRAFANA_URL", DEFAULT_GRAFANA_URL),
        help=f"Grafana base URL. Defaults to {DEFAULT_GRAFANA_URL}.",
    )
    parser.add_argument(
        "--grafana-user",
        default=os.environ.get("GRAFANA_USER", "admin"),
        help="Grafana basic-auth user. Defaults to GRAFANA_USER or admin.",
    )
    parser.add_argument(
        "--grafana-password",
        default=os.environ.get("GRAFANA_PASSWORD", "admin"),
        help="Grafana basic-auth password. Defaults to GRAFANA_PASSWORD or admin.",
    )
    parser.add_argument(
        "--dashboard-uid",
        default=os.environ.get("GRAFANA_DASHBOARD_UID", DEFAULT_DASHBOARD_UID),
        help=f"Grafana dashboard UID. Defaults to {DEFAULT_DASHBOARD_UID}.",
    )
    parser.add_argument(
        "--dashboard-path",
        type=Path,
        default=Path(os.environ.get("DASHBOARD_PATH", DEFAULT_DASHBOARD_PATH)),
        help="Committed dashboard JSON path to compare against Grafana.",
    )
    parser.add_argument(
        "--expected-folder-title",
        default=os.environ.get("GRAFANA_EXPECT_FOLDER_TITLE"),
        help="Optional Grafana folder title expected for the Git-synced dashboard.",
    )
    return parser.parse_args(argv)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SmokeCheckError(f"Dashboard artifact does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise SmokeCheckError(
            f"Dashboard artifact is not valid JSON: {path}"
        ) from error

    if not isinstance(value, dict):
        raise SmokeCheckError(f"Dashboard artifact must contain a JSON object: {path}")
    return value


class GrafanaClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        credentials = f"{username}:{password}".encode("utf-8")
        self.authorization = f"Basic {base64.b64encode(credentials).decode('ascii')}"

    def get_json(self, path: str) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            headers={
                "Accept": "application/json",
                "Authorization": self.authorization,
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise SmokeCheckError(
                f"Grafana GET {path} failed: HTTP {error.code} {body}"
            ) from error
        except URLError as error:
            raise SmokeCheckError(
                f"Grafana GET {path} failed: {error.reason}"
            ) from error
        except json.JSONDecodeError as error:
            raise SmokeCheckError(
                f"Grafana GET {path} did not return valid JSON"
            ) from error

        if not isinstance(value, dict):
            raise SmokeCheckError(
                f"Grafana GET {path} returned a non-object JSON value"
            )
        return value


def compare_dashboard_contract(
    expected: dict[str, Any], actual: dict[str, Any]
) -> None:
    expected_summary = summarize_dashboard(expected)
    actual_summary = summarize_dashboard(actual)
    if actual_summary != expected_summary:
        raise SmokeCheckError(
            "Loaded dashboard does not match the committed dashboard contract:\n"
            f"expected {json.dumps(expected_summary, sort_keys=True)}\n"
            f"actual   {json.dumps(actual_summary, sort_keys=True)}"
        )


def summarize_dashboard(dashboard: dict[str, Any]) -> dict[str, Any]:
    panels = dashboard.get("panels")
    variables = dashboard.get("templating", {}).get("list")
    if not isinstance(panels, list):
        raise SmokeCheckError("Dashboard JSON is missing panels")
    if not isinstance(variables, list):
        raise SmokeCheckError("Dashboard JSON is missing templating variables")

    return {
        "description": dashboard.get("description"),
        "panels": [summarize_panel(panel) for panel in panels],
        "refresh": dashboard.get("refresh"),
        "tags": dashboard.get("tags"),
        "time": dashboard.get("time"),
        "title": dashboard.get("title"),
        "uid": dashboard.get("uid"),
        "variables": [
            {
                "label": variable.get("label"),
                "name": variable.get("name"),
                "type": variable.get("type"),
            }
            for variable in variables
            if isinstance(variable, dict)
        ],
    }


def summarize_panel(panel: Any) -> dict[str, Any]:
    if not isinstance(panel, dict):
        raise SmokeCheckError("Dashboard panel must be a JSON object")

    datasource = panel.get("datasource")
    if not isinstance(datasource, dict):
        raise SmokeCheckError(f"Panel {panel.get('title')!r} is missing a datasource")

    targets = panel.get("targets")
    if not isinstance(targets, list):
        raise SmokeCheckError(f"Panel {panel.get('title')!r} is missing targets")

    return {
        "datasource": summarize_datasource(datasource),
        "gridPos": panel.get("gridPos"),
        "id": panel.get("id"),
        "targets": [summarize_target(target) for target in targets],
        "title": panel.get("title"),
        "type": panel.get("type"),
    }


def summarize_target(target: Any) -> dict[str, Any]:
    if not isinstance(target, dict):
        raise SmokeCheckError("Dashboard target must be a JSON object")

    datasource = target.get("datasource")
    if not isinstance(datasource, dict):
        raise SmokeCheckError(f"Target {target.get('refId')!r} is missing a datasource")

    return {
        "datasource": summarize_datasource(datasource),
        "expr": target.get("expr"),
        "limit": target.get("limit"),
        "query": target.get("query"),
        "queryType": target.get("queryType"),
        "refId": target.get("refId"),
        "tableType": target.get("tableType"),
    }


def summarize_datasource(datasource: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": datasource.get("type"),
        "uid": datasource.get("uid"),
    }


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeCheckError as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(1)
