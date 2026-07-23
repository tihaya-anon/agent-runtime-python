"""Console entry point for the Provider Usage observability smoke test."""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType


def main(argv: Sequence[str] | None = None) -> int:
    module = _load_provider_usage_runner()
    runner_main = getattr(module, "main")
    return int(runner_main(list(argv) if argv is not None else None))


def _load_provider_usage_runner() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[3]
        / "ops"
        / "observability"
        / "acceptance"
        / "run_provider_usage_acceptance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "agent_runtime_python_provider_usage_smoke",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Provider Usage smoke runner: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
