"""Subprocess and environment helpers for observability acceptance smoke runs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class ObservabilitySmokeError(RuntimeError):
    """Raised when the end-to-end observability smoke test fails."""


def compose_up_command(compose_file: Path) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file), "up", "-d", "--build"]


def compose_exec_command(
    compose_file: Path,
    service: str,
    command: list[str],
) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "exec",
        "-T",
        service,
        *command,
    ]


def compose_cp_command(
    compose_file: Path,
    service: str,
    container_path: Path,
    host_path: Path,
) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "cp",
        f"{service}:{container_path}",
        str(host_path),
    ]


def experiment_command(
    python_executable: str,
    runtime_url: str,
    results_path: Path,
    study_id: str,
    params: list[str],
    behavior_versions: list[str] | None = None,
    message: str = "Observability acceptance smoke run.",
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
        message,
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


def shell_join(command: list[str]) -> str:
    return " ".join(command)
