"""HTTP probes for Tempo, Loki, Prometheus, and runtime health."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from smoke_commands import ObservabilitySmokeError
from smoke_results import TrialIdentity


def wait_for_http(url: str, timeout_seconds: float) -> None:
    wait_for(
        description=url,
        timeout_seconds=timeout_seconds,
        probe=lambda: http_json(url) is not None,
    )


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
            (
                f'{{service_name="agent-runtime-python"}} | json '
                f'| attributes_agent_run_id="{success_identity.agent_run_id}"'
            ),
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
