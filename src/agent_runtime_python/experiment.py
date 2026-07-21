"""Experiment performer for repeated Agent Run worker trials."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, TextIO, cast
from urllib.request import Request, urlopen

from agent_runtime_python.observability.telemetry import (
    AgentRunTelemetry,
    configure_telemetry_from_environment,
)
from agent_runtime_python.runtime.protocol import (
    COMMAND_VALIDATOR,
    EVENT_VALIDATOR,
    PROTOCOL_VERSION,
)
from agent_runtime_python.runtime.worker import AgentRunWorker

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


class ExperimentTarget(Protocol):
    def run(self, trial: TrialPlan) -> TargetRun:
        """Execute one trial and return Agent Run stream events."""
        ...


class DirectWorkerTarget:
    def __init__(self, worker: AgentRunWorker | None = None) -> None:
        self._worker = worker or AgentRunWorker()

    def run(self, trial: TrialPlan) -> TargetRun:
        events = self._worker.handle_line(_worker_command_line(trial.command))
        return _worker_target_run(events, trial)


class InternalHttpStreamingTarget:
    def __init__(
        self,
        api_base_url: str,
        open_agent_run: Callable[[Request], Any] | None = None,
    ) -> None:
        self._api_base_url = api_base_url
        self._open_agent_run = open_agent_run or urlopen

    def run(self, trial: TrialPlan) -> TargetRun:
        request = Request(
            url=f"{self._api_base_url.rstrip('/')}/internal/agent-runs",
            data=_json_bytes(trial.command),
            headers={
                "Accept": "application/x-ndjson",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        events = _read_ndjson_worker_events(request, self._open_agent_run)
        return _worker_target_run(events, trial)


class TsGatewayTarget:
    def __init__(
        self,
        api_base_url: str,
        open_agent_run: Callable[[Request], Any] | None = None,
    ) -> None:
        self._api_base_url = api_base_url
        self._open_agent_run = open_agent_run or urlopen

    def run(self, trial: TrialPlan) -> TargetRun:
        request = Request(
            url=f"{self._api_base_url.rstrip('/')}/api/agent-runs",
            data=_json_bytes(trial.command["input"]),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return TargetRun(
            events=_read_ndjson_worker_events(request, self._open_agent_run),
            submitted_runtime_profile_id=None,
            submitted_behavior_version=None,
        )


class JsonlResultRecorder:
    def __init__(self, output_stream: TextIO) -> None:
        self._output_stream = output_stream

    def record(self, result: TrialResult) -> None:
        record = _stable_json_record(_trial_result_to_record(result))
        self._output_stream.write(f"{record}\n")
        self._output_stream.flush()


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


def run_experiment(
    config: ExperimentConfig,
    target: ExperimentTarget | None = None,
    recorder: JsonlResultRecorder | None = None,
    planner: TrialPlanner | None = None,
    telemetry: AgentRunTelemetry | None = None,
) -> list[TrialResult]:
    active_target = target or create_target(config.target)
    active_telemetry = telemetry or AgentRunTelemetry()
    results = []

    with active_telemetry.start_experiment_study(config.study_id, config.target):
        for trial in build_trial_plan(config, planner=planner):
            with active_telemetry.start_experiment_trial(
                config.study_id,
                trial.trial_id,
                config.target,
                trial.parameters,
            ) as span:
                target_run = active_target.run(trial)
                result = record_trial_result(trial, target_run)
                active_telemetry.finish_experiment_trial(span, result.outcome)
                if recorder is not None:
                    recorder.record(result)
                results.append(result)

    return results


def record_trial_result(trial: TrialPlan, target_run: TargetRun) -> TrialResult:
    events = target_run.events
    if not events:
        raise ValueError("Trial target returned no events")

    terminal_event = events[-1]
    terminal_type = terminal_event.get("type")

    return TrialResult(
        trial_id=trial.trial_id,
        agent_run_id=_event_agent_run_id(events, trial.agent_run_id),
        parameters=trial.parameters,
        outcome=_trial_outcome(terminal_type),
        terminal_event=str(terminal_type),
        response_summary=_summarize_response(_response_text(events)),
        requested_runtime_profile_id=_command_runtime_profile_id(trial.command),
        requested_behavior_version=_command_behavior_version(trial.command),
        submitted_runtime_profile_id=target_run.submitted_runtime_profile_id,
        submitted_behavior_version=target_run.submitted_behavior_version,
        error_classification=_optional_text(terminal_event.get("errorClassification")),
    )


def create_target(
    target: TargetKind,
    api_base_url: str = "http://localhost:3000",
) -> ExperimentTarget:
    if target == "direct-worker":
        return DirectWorkerTarget()
    if target == "internal-http":
        return InternalHttpStreamingTarget(api_base_url)

    return TsGatewayTarget(api_base_url)


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
        parameter_matrix=_parse_parameter_matrix(args.param),
        runtime_profile=args.runtime_profile,
        target=args.target,
        behavior_version=_parse_key_value_entries(args.behavior_version),
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


def _build_trial(
    config: ExperimentConfig,
    index: int,
    parameters: dict[str, JsonScalar],
) -> TrialPlan:
    trial_id = f"{config.study_id}-trial-{index:04d}"
    agent_run_id = f"ar_{_identifier_token(trial_id)}"
    command = _build_run_start_command(config, trial_id, agent_run_id, parameters)
    COMMAND_VALIDATOR.validate(command)
    return TrialPlan(
        trial_id=trial_id,
        agent_run_id=agent_run_id,
        parameters=parameters,
        command=command,
    )


def _build_run_start_command(
    config: ExperimentConfig,
    trial_id: str,
    agent_run_id: str,
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
    }


def _runtime_profile(profile: RuntimeProfileKind) -> dict[str, Any]:
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
        raise ValueError(
            f"{message}: {joined_dimensions}",
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
        if not distribution.choices:
            raise ValueError(f"Parameter {distribution.name} must include choices")
        return

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


def _trial_message(message: str, parameters: Mapping[str, JsonScalar]) -> str:
    if not parameters:
        return message

    return f"{message}\n\nTrial parameters: {_stable_json(parameters)}"


def _trial_parameter_version(parameters: Mapping[str, JsonScalar]) -> str:
    return f"trial-parameter:{_hash_text(_stable_json(parameters))}"


def _identifier_token(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _stable_json(value: Mapping[str, JsonScalar]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _stable_json_record(value: Mapping[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _worker_command_line(command: Mapping[str, Any]) -> str:
    return f"{json.dumps(command, separators=(',', ':'))}\n"


def _summarize_response(response_text: str, limit: int = 240) -> str:
    normalized = " ".join(response_text.split())
    if len(normalized) <= limit:
        return normalized

    return normalized[: limit - 1].rstrip() + "..."


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _trial_outcome(terminal_type: object) -> TrialOutcome:
    if terminal_type == "run.completed":
        return "succeeded"
    if terminal_type == "run.cancelled":
        return "cancelled"

    return "failed"


def _response_text(events: Sequence[Mapping[str, Any]]) -> str:
    return "".join(
        str(event["text"])
        for event in events
        if event.get("type") == "message.delta" and isinstance(event.get("text"), str)
    )


def _command_runtime_profile_id(command: Mapping[str, Any]) -> str:
    runtime_profile = command["runtimeProfile"]
    if not isinstance(runtime_profile, Mapping):
        raise TypeError("runtimeProfile must be an object")

    return str(runtime_profile["profileId"])


def _command_behavior_version(command: Mapping[str, Any]) -> dict[str, str]:
    behavior_version = command["behaviorVersion"]
    if not isinstance(behavior_version, Mapping):
        raise TypeError("behaviorVersion must be an object")

    return dict(cast(Mapping[str, str], behavior_version))


def _worker_target_run(
    events: list[dict[str, Any]],
    trial: TrialPlan,
) -> TargetRun:
    return TargetRun(
        events=events,
        submitted_runtime_profile_id=_command_runtime_profile_id(trial.command),
        submitted_behavior_version=_command_behavior_version(trial.command),
    )


def _event_agent_run_id(events: Sequence[Mapping[str, Any]], fallback: str) -> str:
    for event in events:
        if event.get("type") == "run.started":
            agent_run_id = event.get("agentRunId")
            if isinstance(agent_run_id, str):
                return agent_run_id

    return fallback


def _read_ndjson_worker_events(
    request: Request,
    open_agent_run: Callable[[Request], Any],
) -> list[dict[str, Any]]:
    events = []
    with open_agent_run(request) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise RuntimeError(f"Agent Run target returned HTTP {status}")

        for raw_line in response:
            line = _response_line(raw_line)
            if not line.strip():
                continue
            events.append(_decode_worker_event(line))

    return events


def _response_line(raw_line: Any) -> str:
    if isinstance(raw_line, bytes):
        return raw_line.decode("utf-8")

    return str(raw_line)


def _decode_worker_event(line: str) -> dict[str, Any]:
    event = json.loads(line)
    EVENT_VALIDATOR.validate(event)
    return event


def _trial_result_to_record(result: TrialResult) -> dict[str, Any]:
    record = {
        "trialId": result.trial_id,
        "agentRunId": result.agent_run_id,
        "parameters": result.parameters,
        "outcome": result.outcome,
        "terminalEvent": result.terminal_event,
        "responseSummary": result.response_summary,
        "requestedRuntimeProfileId": result.requested_runtime_profile_id,
        "requestedBehaviorVersion": result.requested_behavior_version,
        "submittedRuntimeProfileId": result.submitted_runtime_profile_id,
        "submittedBehaviorVersion": result.submitted_behavior_version,
    }
    if result.error_classification is not None:
        record["errorClassification"] = result.error_classification

    return record


def _parse_parameter_matrix(entries: Sequence[str]) -> dict[str, list[JsonScalar]]:
    if not entries:
        return {"promptStyle": ["concise", "detailed"]}

    matrix = {}
    for entry in entries:
        name, raw_values = _split_key_value_entry(entry)
        values = [_parse_json_scalar(value) for value in raw_values.split(",") if value]
        if not values:
            raise ValueError(f"Parameter {name} must include at least one value")
        matrix[name] = values

    return matrix


def _parse_key_value_entries(entries: Sequence[str]) -> dict[str, str]:
    return dict(_split_key_value_entry(entry) for entry in entries)


def _split_key_value_entry(entry: str) -> tuple[str, str]:
    if "=" not in entry:
        raise ValueError(f"Expected name=value entry, received {entry!r}")

    name, value = entry.split("=", 1)
    if not name.strip():
        raise ValueError(f"Expected non-empty name in {entry!r}")

    return name, value


def _parse_json_scalar(value: str) -> JsonScalar:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value

    if isinstance(parsed, str | int | float | bool):
        return parsed

    raise ValueError(
        f"Parameter values must be strings, numbers, or booleans: {value!r}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
