"""Shared experiment types used by planners, targets, and recorders."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

JsonScalar = str | int | float | bool
ParameterMatrix = Mapping[str, Sequence[JsonScalar]]
RuntimeProfileKind = Literal["development", "published"]
TargetKind = Literal["direct-worker", "internal-http", "ts-gateway"]
ParameterDistributionKind = Literal["categorical", "int", "float"]
TrialOutcome = Literal["succeeded", "failed", "cancelled"]

BEHAVIOR_VERSION_DIMENSIONS = (
    "graph",
    "state",
    "action",
    "prompt",
    "tool",
    "model",
    "trialParameter",
    "sourceRevision",
)


@dataclass(frozen=True)
class ExperimentConfig:
    message: str
    parameter_matrix: ParameterMatrix
    runtime_profile: RuntimeProfileKind = "development"
    target: TargetKind = "direct-worker"
    behavior_version: Mapping[str, str] | None = None
    comparable: bool = False
    study_id: str = "local-sweep"


@dataclass(frozen=True)
class ParameterDistribution:
    name: str
    kind: ParameterDistributionKind
    choices: Sequence[JsonScalar] = ()
    low: int | float | None = None
    high: int | float | None = None
    step: int | float | None = None
    log: bool = False


@dataclass(frozen=True)
class TrialPlan:
    trial_id: str
    agent_run_id: str
    parameters: dict[str, JsonScalar]
    command: dict[str, Any]


@dataclass(frozen=True)
class TrialResult:
    trial_id: str
    agent_run_id: str
    parameters: dict[str, JsonScalar]
    outcome: TrialOutcome
    terminal_event: str
    response_summary: str
    requested_runtime_profile_id: str
    requested_behavior_version: dict[str, str]
    submitted_runtime_profile_id: str | None
    submitted_behavior_version: dict[str, str] | None
    error_classification: str | None = None
    usage: dict[str, int] | None = None
    model_usage: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class UsageSnapshot:
    usage: dict[str, int]
    model_usage: list[dict[str, Any]]


@dataclass(frozen=True)
class TargetRun:
    events: list[dict[str, Any]]
    submitted_runtime_profile_id: str | None
    submitted_behavior_version: dict[str, str] | None


class TrialPlanner(Protocol):
    def parameter_sets(
        self, config: ExperimentConfig
    ) -> Sequence[dict[str, JsonScalar]]:
        """Generate parameter sets for a trial study."""
        ...


class OptunaTrialProtocol(Protocol):
    def suggest_categorical(
        self,
        name: str,
        choices: Sequence[JsonScalar],
    ) -> JsonScalar:
        """Suggest one categorical value from an Optuna trial."""
        ...

    def suggest_int(
        self,
        name: str,
        low: int,
        high: int,
        step: int = 1,
        log: bool = False,
    ) -> int:
        """Suggest one integer value from an Optuna trial."""
        ...

    def suggest_float(
        self,
        name: str,
        low: float,
        high: float,
        step: float | None = None,
        log: bool = False,
    ) -> float:
        """Suggest one floating-point value from an Optuna trial."""
        ...


class OptunaStudyProtocol(Protocol):
    def ask(self) -> OptunaTrialProtocol:
        """Allocate one Optuna trial."""
        ...


class ExperimentTarget(Protocol):
    def run(self, trial: TrialPlan) -> TargetRun:
        """Execute one trial and return Agent Run stream events."""
        ...
