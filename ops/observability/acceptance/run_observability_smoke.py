#!/usr/bin/env python3
"""Run a local PGL-backed observability smoke test for the Python runtime."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ACCEPTANCE_DIR = Path(__file__).resolve().parent
if str(ACCEPTANCE_DIR) not in sys.path:
    sys.path.insert(0, str(ACCEPTANCE_DIR))

import smoke_dashboard
from smoke_commands import (
    ObservabilitySmokeError,
    compose_cp_command,
    compose_exec_command,
    compose_up_command,
    experiment_command,
    experiment_environment,
    failed_results_path,
    run_command,
    shell_join,
)
from smoke_results import (
    TrialIdentity,
    print_dashboard_values,
    read_trial_identities,
)
from smoke_telemetry import (
    http_json,
    loki_has_log,
    prometheus_has_samples,
    tempo_has_trace,
    wait_for,
    wait_for_http,
    wait_for_telemetry,
)

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "compose.observability.yaml"
DEFAULT_RESULTS_PATH = Path("/tmp/agent-runtime-python-observability-smoke.jsonl")
DEFAULT_RUNTIME_URL = "http://127.0.0.1:8088"
DEFAULT_OTLP_ENDPOINT = "http://127.0.0.1:4318"
DEFAULT_TEMPO_URL = "http://127.0.0.1:3200"
DEFAULT_LOKI_URL = "http://127.0.0.1:3100"
DEFAULT_PROMETHEUS_URL = "http://127.0.0.1:9090"
GRAPH_ID = "graph:python-smoke"
FAILED_GRAPH_ID = "graph:observability-smoke-unsupported"

__all__ = [
    "ObservabilitySmokeError",
    "TrialIdentity",
    "compose_cp_command",
    "compose_exec_command",
    "compose_up_command",
    "experiment_command",
    "experiment_environment",
    "failed_results_path",
    "http_json",
    "loki_has_log",
    "main",
    "print_dashboard_values",
    "prometheus_has_samples",
    "read_trial_identities",
    "run_command",
    "shell_join",
    "tempo_has_trace",
    "wait_for",
    "wait_for_http",
    "wait_for_telemetry",
]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    study_id = args.study_id or timestamped_study_id()

    run_command(compose_up_command(args.compose_file))
    wait_for_http(f"{args.runtime_url.rstrip('/')}/healthz", args.startup_timeout)

    success_results_path = args.results_path
    failure_results_path = failed_results_path(args.results_path)
    run_success_trials(args, success_results_path, study_id)
    run_failure_trials(args, failure_results_path, f"{study_id}-failure")

    success_identities = read_trial_identities(success_results_path, study_id)
    failure_identities = read_trial_identities(
        failure_results_path,
        f"{study_id}-failure",
    )
    require_trial_records(success_identities, success_results_path, "successful")
    require_trial_records(failure_identities, failure_results_path, "failed")

    smoke_dashboard.main(grafana_args(args))
    wait_for_telemetry(args, success_identities[0], failure_identities[0])
    print_dashboard_values(success_identities, failure_identities[0])
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start the runtime compose service, run internal HTTP experiment trials, "
            "and verify that PGL receives traces, logs, and span metrics."
        )
    )
    parser.add_argument("--compose-file", type=Path, default=COMPOSE_FILE)
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL)
    parser.add_argument("--otlp-endpoint", default=DEFAULT_OTLP_ENDPOINT)
    parser.add_argument("--tempo-url", default=DEFAULT_TEMPO_URL)
    parser.add_argument("--loki-url", default=DEFAULT_LOKI_URL)
    parser.add_argument("--prometheus-url", default=DEFAULT_PROMETHEUS_URL)
    parser.add_argument("--grafana-url", default=smoke_dashboard.DEFAULT_GRAFANA_URL)
    parser.add_argument(
        "--grafana-user",
        default=os.environ.get("GRAFANA_USER", "admin"),
    )
    parser.add_argument(
        "--grafana-password",
        default=os.environ.get("GRAFANA_PASSWORD", "admin"),
    )
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument(
        "--study-id", default=os.environ.get("OBSERVABILITY_SMOKE_STUDY_ID")
    )
    parser.add_argument("--startup-timeout", type=float, default=90.0)
    parser.add_argument("--telemetry-timeout", type=float, default=120.0)
    return parser.parse_args(argv)


def timestamped_study_id() -> str:
    return f"observability-smoke-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"


def run_success_trials(
    args: argparse.Namespace,
    results_path: Path,
    study_id: str,
) -> None:
    run_command(
        experiment_command(
            python_executable=sys.executable,
            runtime_url=args.runtime_url,
            results_path=results_path,
            study_id=study_id,
            params=["promptStyle=concise,detailed"],
        ),
        env=experiment_environment(args.otlp_endpoint),
    )


def run_failure_trials(
    args: argparse.Namespace,
    results_path: Path,
    study_id: str,
) -> None:
    run_command(
        experiment_command(
            python_executable=sys.executable,
            runtime_url=args.runtime_url,
            results_path=results_path,
            study_id=study_id,
            params=["scenario=unsupportedGraph"],
            behavior_versions=[f"graph={FAILED_GRAPH_ID}"],
        ),
        env=experiment_environment(args.otlp_endpoint),
    )


def require_trial_records(
    identities: list[TrialIdentity],
    results_path: Path,
    outcome_label: str,
) -> None:
    if not identities:
        raise ObservabilitySmokeError(
            f"No {outcome_label} trial records were written to {results_path}"
        )


def grafana_args(args: argparse.Namespace) -> list[str]:
    return [
        "--grafana-url",
        args.grafana_url,
        "--grafana-user",
        args.grafana_user,
        "--grafana-password",
        args.grafana_password,
    ]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ObservabilitySmokeError as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(1)
