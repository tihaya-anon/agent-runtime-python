#!/usr/bin/env python3
"""Run a local PGL-backed observability smoke test for the Python runtime."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ACCEPTANCE_DIR = Path(__file__).resolve().parent
if str(ACCEPTANCE_DIR) not in sys.path:
    sys.path.insert(0, str(ACCEPTANCE_DIR))

import smoke_dashboard

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


@dataclass(frozen=True)
class TrialIdentity:
    study_id: str
    trial_id: str
    agent_run_id: str


class ObservabilitySmokeError(RuntimeError):
    """Raised when the end-to-end observability smoke test fails."""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    study_id = args.study_id or timestamped_study_id()

    run_command(compose_up_command(args.compose_file))
    wait_for_http(f"{args.runtime_url.rstrip('/')}/healthz", args.startup_timeout)

    success_results_path = args.results_path
    failure_results_path = failed_results_path(args.results_path)
    run_command(
        experiment_command(
            python_executable=sys.executable,
            runtime_url=args.runtime_url,
            results_path=success_results_path,
            study_id=study_id,
            params=["promptStyle=concise,detailed"],
        ),
        env=experiment_environment(args.otlp_endpoint),
    )
    run_command(
        experiment_command(
            python_executable=sys.executable,
            runtime_url=args.runtime_url,
            results_path=failure_results_path,
            study_id=f"{study_id}-failure",
            params=["scenario=unsupportedGraph"],
            behavior_versions=[f"graph={FAILED_GRAPH_ID}"],
        ),
        env=experiment_environment(args.otlp_endpoint),
    )

    success_identities = read_trial_identities(success_results_path, study_id)
    failure_identities = read_trial_identities(
        failure_results_path,
        f"{study_id}-failure",
    )
    if not success_identities:
        raise ObservabilitySmokeError(
            f"No successful trial records were written to {success_results_path}"
        )
    if not failure_identities:
        raise ObservabilitySmokeError(
            f"No failed trial records were written to {failure_results_path}"
        )

    smoke_dashboard.main(
        [
            "--grafana-url",
            args.grafana_url,
            "--grafana-user",
            args.grafana_user,
            "--grafana-password",
            args.grafana_password,
        ]
    )
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


def compose_up_command(compose_file: Path) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file), "up", "-d", "--build"]


def experiment_command(
    python_executable: str,
    runtime_url: str,
    results_path: Path,
    study_id: str,
    params: list[str],
    behavior_versions: list[str] | None = None,
) -> list[str]:
    command = [
        python_executable,
        "-m",
        "agent_runtime_python.experiment",
        "--target",
        "internal-http",
        "--api-base-url",
        runtime_url,
        "--study-id",
        study_id,
        "--message",
        "Observability acceptance smoke run.",
        "--output",
        str(results_path),
    ]
    for param in params:
        command.extend(["--param", param])
    for behavior_version in behavior_versions or []:
        command.extend(["--behavior-version", behavior_version])

    return command


def failed_results_path(results_path: Path) -> Path:
    return results_path.with_name(f"{results_path.stem}-failed{results_path.suffix}")


def experiment_environment(otlp_endpoint: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "OTEL_EXPORTER_OTLP_ENDPOINT": otlp_endpoint,
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_SERVICE_NAME": "agent-runtime-python",
            "OTEL_TRACES_EXPORTER": "otlp",
        }
    )
    return env


def run_command(command: list[str], env: dict[str, str] | None = None) -> None:
    print(f"Running: {shell_join(command)}")
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise ObservabilitySmokeError(
            f"Command failed with exit code {completed.returncode}: {shell_join(command)}"
        )


def wait_for_http(url: str, timeout_seconds: float) -> None:
    wait_for(
        description=url,
        timeout_seconds=timeout_seconds,
        probe=lambda: http_json(url) is not None,
    )


def read_trial_identities(path: Path, study_id: str) -> list[TrialIdentity]:
    identities = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        trial_id = record.get("trialId")
        agent_run_id = record.get("agentRunId")
        if not isinstance(trial_id, str) or not isinstance(agent_run_id, str):
            raise ObservabilitySmokeError(f"Invalid trial result record: {line}")
        identities.append(
            TrialIdentity(
                study_id=study_id,
                trial_id=trial_id,
                agent_run_id=agent_run_id,
            )
        )

    return identities


def wait_for_telemetry(
    args: argparse.Namespace,
    success_identity: TrialIdentity,
    failure_identity: TrialIdentity,
) -> None:
    wait_for(
        description="experiment.trial trace",
        timeout_seconds=args.telemetry_timeout,
        probe=lambda: tempo_has_trace(
            args.tempo_url,
            (
                f'{{ resource.service.name = "agent-runtime-python" '
                f'&& span:name = "experiment.trial" '
                f'&& span."metadata.experiment.study_id" = "{success_identity.study_id}" }}'
            ),
        ),
    )
    wait_for(
        description="agent.run trace",
        timeout_seconds=args.telemetry_timeout,
        probe=lambda: tempo_has_trace(
            args.tempo_url,
            (
                f'{{ resource.service.name = "agent-runtime-python" '
                f'&& span:name = "agent.run" '
                f'&& span."session.id" = "{success_identity.agent_run_id}" }}'
            ),
        ),
    )
    wait_for(
        description="failed agent.run trace",
        timeout_seconds=args.telemetry_timeout,
        probe=lambda: tempo_has_trace(
            args.tempo_url,
            (
                f'{{ resource.service.name = "agent-runtime-python" '
                f'&& span:name = "agent.run" '
                f'&& span."session.id" = "{failure_identity.agent_run_id}" '
                f'&& span."metadata.agent_run.outcome" = "failed" }}'
            ),
        ),
    )
    wait_for(
        description="runtime request log",
        timeout_seconds=args.telemetry_timeout,
        probe=lambda: loki_has_log(
            args.loki_url,
            f'{{service_name="agent-runtime-python"}} | json | agent_run_id="{success_identity.agent_run_id}"',
        ),
    )
    wait_for(
        description="agent.run span metric",
        timeout_seconds=args.telemetry_timeout,
        probe=lambda: prometheus_has_samples(
            args.prometheus_url,
            'traces_spanmetrics_calls_total{service="agent-runtime-python",span_name="agent.run"}',
        ),
    )


def tempo_has_trace(base_url: str, traceql: str) -> bool:
    response = http_json(
        f"{base_url.rstrip('/')}/api/search?limit=20&q={quote(traceql, safe='')}"
    )
    traces = response.get("traces") if isinstance(response, dict) else None
    return isinstance(traces, list) and len(traces) > 0


def loki_has_log(base_url: str, logql: str) -> bool:
    response = http_json(
        f"{base_url.rstrip('/')}/loki/api/v1/query_range?limit=20&query={quote(logql, safe='')}"
    )
    result = (
        response.get("data", {}).get("result") if isinstance(response, dict) else None
    )
    return isinstance(result, list) and len(result) > 0


def prometheus_has_samples(base_url: str, promql: str) -> bool:
    response = http_json(
        f"{base_url.rstrip('/')}/api/v1/query?query={quote(promql, safe='')}"
    )
    result = (
        response.get("data", {}).get("result") if isinstance(response, dict) else None
    )
    return isinstance(result, list) and len(result) > 0


def http_json(url: str) -> dict[str, Any] | None:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=5) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError):
        return None

    return value if isinstance(value, dict) else None


def wait_for(
    description: str,
    timeout_seconds: float,
    probe: Callable[[], bool],
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if probe():
            print(f"{description}: ok")
            return
        time.sleep(2)

    raise ObservabilitySmokeError(f"Timed out waiting for {description}")


def print_dashboard_values(
    success_identities: list[TrialIdentity],
    failure_identity: TrialIdentity,
) -> None:
    first = success_identities[0]
    print("\nDashboard variable values:")
    print(f"study_id={first.study_id}")
    print(f"trial_id={first.trial_id}")
    print(f"graph_id={GRAPH_ID}")
    print(f"agent_run_id={first.agent_run_id}")
    print(f"failed_agent_run_id={failure_identity.agent_run_id}")
    print(f"failed_study_id={failure_identity.study_id}")
    print("\nAll generated trials:")
    for identity in success_identities:
        print(f"- trial_id={identity.trial_id} agent_run_id={identity.agent_run_id}")
    print(
        "- "
        f"trial_id={failure_identity.trial_id} "
        f"agent_run_id={failure_identity.agent_run_id} "
        "outcome=failed"
    )


def shell_join(command: list[str]) -> str:
    return " ".join(command)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ObservabilitySmokeError as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(1)
