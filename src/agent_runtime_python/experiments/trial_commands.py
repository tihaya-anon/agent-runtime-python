"""Worker command construction for experiment trials."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_runtime_python.experiments.serialization import hash_text, stable_json
from agent_runtime_python.experiments.types import (
    BEHAVIOR_VERSION_DIMENSIONS,
    ExperimentConfig,
    JsonScalar,
)
from agent_runtime_python.runtime.protocol import PROTOCOL_VERSION


def build_run_start_command(
    config: ExperimentConfig,
    agent_run_id: str,
    trial_id: str,
    parameters: dict[str, JsonScalar],
) -> dict[str, Any]:
    behavior_version = _build_behavior_version(
        config.behavior_version or {}, parameters
    )
    runtime_profile = _runtime_profile(config.runtime_profile)
    if config.runtime_profile == "published" or config.comparable:
        _require_complete_behavior_version(behavior_version)

    return {
        "version": PROTOCOL_VERSION,
        "type": "run.start",
        "agentRunId": agent_run_id,
        "input": {"message": _trial_message(config.message, parameters)},
        "runtimeProfile": runtime_profile,
        "behaviorVersion": behavior_version,
        "experimentMetadata": {
            "studyId": config.study_id,
            "trialId": trial_id,
            "target": config.target,
        },
    }


def _runtime_profile(profile: str) -> dict[str, Any]:
    if profile == "published":
        return {
            "schemaVersion": 1,
            "profileId": "runtime-published",
            "runtimePolicy": {
                "agentBehaviorVersion": {
                    "policy": "strict",
                    "requireCompleteDimensions": True,
                    "rejectUnresolvedDimensions": True,
                    "allowIncompleteAdHocRuns": False,
                },
                "sourceRevision": {"requireCleanForPublishedGraphVersions": True},
            },
        }

    return {
        "schemaVersion": 1,
        "profileId": "runtime-development",
        "runtimePolicy": {
            "agentBehaviorVersion": {
                "policy": "development",
                "requireCompleteDimensions": False,
                "rejectUnresolvedDimensions": False,
                "allowIncompleteAdHocRuns": True,
                "incompleteAdHocRuns": {"comparable": False, "promotable": False},
            },
            "sourceRevision": {"requireCleanForPublishedGraphVersions": False},
        },
    }


def _build_behavior_version(
    base_behavior_version: Mapping[str, str],
    parameters: Mapping[str, JsonScalar],
) -> dict[str, str]:
    behavior_version = dict(base_behavior_version)
    behavior_version.setdefault("graph", "graph:python-smoke")
    behavior_version["trialParameter"] = _trial_parameter_version(parameters)
    return behavior_version


def _require_complete_behavior_version(behavior_version: Mapping[str, str]) -> None:
    missing_dimensions = [
        dimension
        for dimension in BEHAVIOR_VERSION_DIMENSIONS
        if not behavior_version.get(dimension)
    ]
    if missing_dimensions:
        joined_dimensions = ", ".join(missing_dimensions)
        message = "Comparable and published trials require complete behavior identity"
        raise ValueError(f"{message}: {joined_dimensions}")


def _trial_message(message: str, parameters: Mapping[str, JsonScalar]) -> str:
    if not parameters:
        return message

    return f"{message}\n\nTrial parameters: {stable_json(parameters)}"


def _trial_parameter_version(parameters: Mapping[str, JsonScalar]) -> str:
    return f"trial-parameter:{hash_text(stable_json(parameters))}"
