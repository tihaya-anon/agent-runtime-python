#!/usr/bin/env python3
"""Verify Provider Usage appears in JSONL results and PGL traces."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ACCEPTANCE_DIR = Path(__file__).resolve().parent
if str(ACCEPTANCE_DIR) not in sys.path:
    sys.path.insert(0, str(ACCEPTANCE_DIR))

from smoke_commands import (
    ObservabilitySmokeError,
    compose_up_command,
    experiment_command,
    experiment_environment,
    run_command,
)
from smoke_results import TrialIdentity, read_trial_identities
from smoke_telemetry import (
    prometheus_has_samples,
    tempo_has_trace,
    wait_for,
    wait_for_http,
)

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "compose.observability.yaml"
DEFAULT_RESULTS_PATH = Path("/tmp/agent-runtime-python-provider-usage-acceptance.jsonl")
DEFAULT_RUNTIME_URL = "http://127.0.0.1:8088"
DEFAULT_OTLP_ENDPOINT = "http://127.0.0.1:4318"
DEFAULT_TEMPO_URL = "http://127.0.0.1:3200"
DEFAULT_PROMETHEUS_URL = "http://127.0.0.1:9090"
USAGE_GRAPH_ID = "graph:python-smoke-usage"
USAGE_NODE_NAME = "draft_response"
EXPECTED_USAGE = {
    "inputTokens": 11,
    "outputTokens": 7,
    "totalTokens": 18,
    "cachedInputTokens": 3,
    "cacheCreationInputTokens": 2,
    "reasoningOutputTokens": 1,
}
EXPECTED_MODEL_USAGE = {
    "provider": "synthetic",
    "model": "model:deterministic-smoke",
    "graphId": USAGE_GRAPH_ID,
    "nodeName": USAGE_NODE_NAME,
    **EXPECTED_USAGE,
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    study_id = args.study_id or timestamped_study_id()

    run_command(compose_up_command(args.compose_file))
    wait_for_http(f"{args.runtime_url.rstrip('/')}/healthz", args.startup_timeout)

    run_command(
        experiment_command(
            python_executable=sys.executable,
            runtime_url=args.runtime_url,
            results_path=args.results_path,
            study_id=study_id,
            params=["promptStyle=concise"],
            behavior_versions=[f"graph={USAGE_GRAPH_ID}"],
        ),
        env=experiment_environment(args.otlp_endpoint),
    )

    record = read_single_result(args.results_path)
    require_usage_record(record, args.results_path)
    identity = read_trial_identities(args.results_path, study_id)[0]
    wait_for_provider_usage_traces(args, identity)
    print_acceptance_values(args.results_path, identity)
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the synthetic usage graph and verify Provider Usage is present "
            "in both JSONL trial results and PGL Tempo traces."
        )
    )
    parser.add_argument("--compose-file", type=Path, default=COMPOSE_FILE)
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL)
    parser.add_argument("--otlp-endpoint", default=DEFAULT_OTLP_ENDPOINT)
    parser.add_argument("--tempo-url", default=DEFAULT_TEMPO_URL)
    parser.add_argument("--prometheus-url", default=DEFAULT_PROMETHEUS_URL)
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument(
        "--study-id",
        default=os.environ.get("PROVIDER_USAGE_ACCEPTANCE_STUDY_ID"),
    )
    parser.add_argument("--startup-timeout", type=float, default=90.0)
    parser.add_argument("--telemetry-timeout", type=float, default=120.0)
    return parser.parse_args(argv)


def timestamped_study_id() -> str:
    return f"provider-usage-acceptance-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"


def read_single_result(results_path: Path) -> dict[str, Any]:
    records = [
        json.loads(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(records) != 1:
        raise ObservabilitySmokeError(
            f"Expected one trial result in {results_path}, found {len(records)}"
        )

    record = records[0]
    if not isinstance(record, dict):
        raise ObservabilitySmokeError(f"Invalid trial result record in {results_path}")

    return record


def require_usage_record(record: dict[str, Any], results_path: Path) -> None:
    usage = record.get("usage")
    if usage != EXPECTED_USAGE:
        raise ObservabilitySmokeError(
            f"Unexpected usage in {results_path}: {json.dumps(usage, sort_keys=True)}"
        )

    model_usage = record.get("modelUsage")
    if model_usage != [EXPECTED_MODEL_USAGE]:
        raise ObservabilitySmokeError(
            "Unexpected modelUsage in "
            f"{results_path}: {json.dumps(model_usage, sort_keys=True)}"
        )

    print("JSONL Provider Usage result: ok")


def wait_for_provider_usage_traces(
    args: argparse.Namespace,
    identity: TrialIdentity,
) -> None:
    wait_for(
        description="agent.run usage trace",
        timeout_seconds=args.telemetry_timeout,
        probe=lambda: tempo_has_trace(
            args.tempo_url,
            (
                f'{{ resource.service.name = "agent-runtime-python" '
                f'&& span:name = "agent.run" '
                f'&& span."session.id" = "{identity.agent_run_id}" '
                f'&& span."usage.inputTokens" = 11 '
                f'&& span."usage.totalTokens" = 18 }}'
            ),
        ),
    )
    wait_for(
        description="gen_ai model usage trace",
        timeout_seconds=args.telemetry_timeout,
        probe=lambda: tempo_has_trace(
            args.tempo_url,
            (
                f'{{ resource.service.name = "agent-runtime-python" '
                f'&& span:name = "gen_ai.inference.client" '
                f'&& span."session.id" = "{identity.agent_run_id}" '
                f'&& span."gen_ai.system" = "synthetic" '
                f'&& span."gen_ai.request.model" = "model:deterministic-smoke" '
                f'&& span."gen_ai.usage.input_tokens" = 11 '
                f'&& span."gen_ai.usage.total_tokens" = 18 '
                f'&& span."metadata.agent_graph.id" = "{USAGE_GRAPH_ID}" '
                f'&& span."graph.node.name" = "{USAGE_NODE_NAME}" }}'
            ),
        ),
    )
    wait_for(
        description="gen_ai model latency p95 metric",
        timeout_seconds=args.telemetry_timeout,
        probe=lambda: prometheus_has_samples(
            args.prometheus_url,
            (
                "histogram_quantile(0.95, sum by (le, span_name) "
                "(rate(traces_spanmetrics_latency_bucket"
                '{service="agent-runtime-python",'
                'span_name="gen_ai.inference.client"}[1h])))'
            ),
        ),
    )


def print_acceptance_values(results_path: Path, identity: TrialIdentity) -> None:
    print("\nProvider Usage acceptance values:")
    print(f"results_path={results_path}")
    print(f"study_id={identity.study_id}")
    print(f"trial_id={identity.trial_id}")
    print(f"agent_run_id={identity.agent_run_id}")
    print(f"graph_id={USAGE_GRAPH_ID}")
    print(f"node_name={USAGE_NODE_NAME}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ObservabilitySmokeError as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(1)
