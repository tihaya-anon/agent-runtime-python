"""High-level experiment orchestration."""

from __future__ import annotations

from agent_runtime_python.experiments.planning import build_trial_plan
from agent_runtime_python.experiments.results import (
    JsonlResultRecorder,
    record_trial_result,
)
from agent_runtime_python.experiments.targets import create_target
from agent_runtime_python.experiments.types import (
    ExperimentConfig,
    ExperimentTarget,
    TrialPlanner,
    TrialResult,
)
from agent_runtime_python.observability.telemetry import AgentRunTelemetry


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
