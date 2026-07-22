"""Trial planning and runtime-profile command construction."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import product

from agent_runtime_python.experiments.serialization import identifier_token
from agent_runtime_python.experiments.trial_commands import build_run_start_command
from agent_runtime_python.experiments.types import (
    ExperimentConfig,
    JsonScalar,
    OptunaStudyProtocol,
    OptunaTrialProtocol,
    ParameterDistribution,
    ParameterMatrix,
    TrialPlan,
    TrialPlanner,
)
from agent_runtime_python.runtime.protocol import COMMAND_VALIDATOR


class ParameterSweepPlanner:
    def parameter_sets(
        self, config: ExperimentConfig
    ) -> Sequence[dict[str, JsonScalar]]:
        return _parameter_combinations(config.parameter_matrix)


class OptunaStudyPlanner:
    """Generate parameter sets from an Optuna-compatible study/search space."""

    def __init__(
        self,
        search_space: Sequence[ParameterDistribution],
        trial_count: int,
        study: OptunaStudyProtocol | None = None,
    ) -> None:
        if trial_count < 1:
            raise ValueError("Optuna study trial_count must be positive")
        for distribution in search_space:
            _validate_distribution(distribution)

        self._search_space = tuple(search_space)
        self._trial_count = trial_count
        self._study = study

    def parameter_sets(
        self,
        config: ExperimentConfig,
    ) -> Sequence[dict[str, JsonScalar]]:
        _ = config
        return [self._parameter_set(index) for index in range(self._trial_count)]

    def _parameter_set(self, index: int) -> dict[str, JsonScalar]:
        trial = self._study.ask() if self._study is not None else None
        return {
            distribution.name: _suggest_parameter_value(
                distribution,
                index,
                self._trial_count,
                trial,
            )
            for distribution in self._search_space
        }


def build_trial_plan(
    config: ExperimentConfig,
    planner: TrialPlanner | None = None,
) -> list[TrialPlan]:
    if not config.message.strip():
        raise ValueError("Experiment message must not be empty")

    active_planner = planner or ParameterSweepPlanner()
    return [
        _build_trial(config, index, parameters)
        for index, parameters in enumerate(
            active_planner.parameter_sets(config),
            start=1,
        )
    ]


def _build_trial(
    config: ExperimentConfig,
    index: int,
    parameters: dict[str, JsonScalar],
) -> TrialPlan:
    trial_id = f"{config.study_id}-trial-{index:04d}"
    agent_run_id = f"ar_{identifier_token(trial_id)}"
    command = build_run_start_command(config, agent_run_id, trial_id, parameters)
    COMMAND_VALIDATOR.validate(command)
    return TrialPlan(
        trial_id=trial_id,
        agent_run_id=agent_run_id,
        parameters=parameters,
        command=command,
    )


def _parameter_combinations(
    parameter_matrix: ParameterMatrix,
) -> list[dict[str, JsonScalar]]:
    if not parameter_matrix:
        return [{}]

    parameter_items = _validated_parameter_items(parameter_matrix)
    parameter_names = [name for name, _values in parameter_items]
    value_sets = [values for _name, values in parameter_items]
    return [
        dict(zip(parameter_names, values, strict=True))
        for values in product(*value_sets)
    ]


def _validated_parameter_items(
    parameter_matrix: ParameterMatrix,
) -> list[tuple[str, Sequence[JsonScalar]]]:
    items = []
    for name, values in parameter_matrix.items():
        if not name.strip():
            raise ValueError("Parameter names must not be empty")
        if not values:
            raise ValueError(f"Parameter {name} must include at least one value")
        items.append((name, values))

    return items


def _validate_distribution(distribution: ParameterDistribution) -> None:
    if not distribution.name.strip():
        raise ValueError("Parameter distribution names must not be empty")
    if distribution.kind == "categorical":
        _validate_categorical_distribution(distribution)
        return

    _validate_numeric_distribution(distribution)


def _validate_categorical_distribution(distribution: ParameterDistribution) -> None:
    if not distribution.choices:
        raise ValueError(f"Parameter {distribution.name} must include choices")


def _validate_numeric_distribution(distribution: ParameterDistribution) -> None:
    if distribution.low is None or distribution.high is None:
        raise ValueError(f"Parameter {distribution.name} must define low and high")
    if distribution.low > distribution.high:
        raise ValueError(f"Parameter {distribution.name} low must not exceed high")
    if distribution.kind == "int" and not isinstance(distribution.low, int):
        raise ValueError(f"Parameter {distribution.name} low must be an int")
    if distribution.kind == "int" and not isinstance(distribution.high, int):
        raise ValueError(f"Parameter {distribution.name} high must be an int")


def _suggest_parameter_value(
    distribution: ParameterDistribution,
    trial_index: int,
    trial_count: int,
    trial: OptunaTrialProtocol | None,
) -> JsonScalar:
    if distribution.kind == "categorical":
        return _suggest_categorical(distribution, trial_index, trial)
    if distribution.kind == "int":
        return _suggest_int(distribution, trial_index, trial)

    return _suggest_float(distribution, trial_index, trial_count, trial)


def _suggest_categorical(
    distribution: ParameterDistribution,
    trial_index: int,
    trial: OptunaTrialProtocol | None,
) -> JsonScalar:
    if trial is not None:
        return trial.suggest_categorical(distribution.name, distribution.choices)

    return distribution.choices[trial_index % len(distribution.choices)]


def _suggest_int(
    distribution: ParameterDistribution,
    trial_index: int,
    trial: OptunaTrialProtocol | None,
) -> int:
    low = _required_int(distribution.low)
    high = _required_int(distribution.high)
    step = int(distribution.step or 1)
    if trial is not None:
        return trial.suggest_int(distribution.name, low, high, step, distribution.log)

    values = range(low, high + 1, step)
    return values[trial_index % len(values)]


def _suggest_float(
    distribution: ParameterDistribution,
    trial_index: int,
    trial_count: int,
    trial: OptunaTrialProtocol | None,
) -> float:
    low = _required_float(distribution.low)
    high = _required_float(distribution.high)
    step = float(distribution.step) if distribution.step is not None else None
    if trial is not None:
        return trial.suggest_float(distribution.name, low, high, step, distribution.log)
    if step is not None:
        value_count = int((high - low) // step) + 1
        return low + step * (trial_index % value_count)
    if trial_count == 1:
        return low + ((high - low) / 2)

    return low + ((high - low) * trial_index / (trial_count - 1))


def _required_int(value: int | float | None) -> int:
    if not isinstance(value, int):
        raise ValueError("Expected integer parameter distribution bound")

    return value


def _required_float(value: int | float | None) -> float:
    if value is None:
        raise ValueError("Expected numeric parameter distribution bound")

    return float(value)
