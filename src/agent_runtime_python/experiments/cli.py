"""Command-line entry point for local experiment sweeps."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from agent_runtime_python.experiments.results import JsonlResultRecorder
from agent_runtime_python.experiments.runner import run_experiment
from agent_runtime_python.experiments.serialization import (
    parse_key_value_entries,
    parse_parameter_matrix,
)
from agent_runtime_python.experiments.targets import create_target
from agent_runtime_python.experiments.types import ExperimentConfig
from agent_runtime_python.observability.telemetry import (
    configure_telemetry_from_environment,
)


def main(argv: Sequence[str] | None = None) -> int:
    configure_telemetry_from_environment()

    parser = argparse.ArgumentParser(description="Run a local Agent Run trial sweep.")
    parser.add_argument("--message", default="Explain closures.")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Parameter values as name=a,b,c.",
    )
    parser.add_argument(
        "--runtime-profile",
        choices=["development", "published"],
        default="development",
    )
    parser.add_argument(
        "--target",
        choices=["direct-worker", "internal-http", "ts-gateway"],
        default="direct-worker",
    )
    parser.add_argument("--api-base-url", default="http://localhost:3000")
    parser.add_argument("--study-id", default="local-sweep")
    parser.add_argument("--comparable", action="store_true")
    parser.add_argument(
        "--behavior-version",
        action="append",
        default=[],
        help="Dimension as name=value.",
    )
    parser.add_argument("--output", type=Path, default=Path("trial-results.jsonl"))
    args = parser.parse_args(argv)

    config = ExperimentConfig(
        message=args.message,
        parameter_matrix=parse_parameter_matrix(args.param),
        runtime_profile=args.runtime_profile,
        target=args.target,
        behavior_version=parse_key_value_entries(args.behavior_version),
        comparable=args.comparable,
        study_id=args.study_id,
    )

    target = create_target(config.target, args.api_base_url)
    with args.output.open("w", encoding="utf-8") as output_stream:
        results = run_experiment(
            config,
            target=target,
            recorder=JsonlResultRecorder(output_stream),
        )

    print(f"Recorded {len(results)} trial result(s) in {args.output}")
    return 0
