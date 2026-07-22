"""Trial result normalization and JSONL recording."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TextIO, cast

from agent_runtime_python.experiments.serialization import (
    optional_text,
    stable_json_record,
    summarize_response,
)
from agent_runtime_python.experiments.targets import (
    command_behavior_version,
    command_runtime_profile_id,
)
from agent_runtime_python.experiments.types import (
    TargetRun,
    TrialOutcome,
    TrialPlan,
    TrialResult,
    UsageSnapshot,
)


class JsonlResultRecorder:
    def __init__(self, output_stream: TextIO) -> None:
        self._output_stream = output_stream

    def record(self, result: TrialResult) -> None:
        record = stable_json_record(_trial_result_to_record(result))
        self._output_stream.write(f"{record}\n")
        self._output_stream.flush()


def record_trial_result(trial: TrialPlan, target_run: TargetRun) -> TrialResult:
    events = target_run.events
    if not events:
        raise ValueError("Trial target returned no events")

    terminal_event = events[-1]
    terminal_type = terminal_event.get("type")
    usage_snapshot = _final_usage_snapshot(events)

    return TrialResult(
        trial_id=trial.trial_id,
        agent_run_id=_event_agent_run_id(events, trial.agent_run_id),
        parameters=trial.parameters,
        outcome=_trial_outcome(terminal_type),
        terminal_event=str(terminal_type),
        response_summary=summarize_response(_response_text(events)),
        requested_runtime_profile_id=command_runtime_profile_id(trial.command),
        requested_behavior_version=command_behavior_version(trial.command),
        submitted_runtime_profile_id=target_run.submitted_runtime_profile_id,
        submitted_behavior_version=target_run.submitted_behavior_version,
        error_classification=optional_text(terminal_event.get("errorClassification")),
        usage=usage_snapshot.usage if usage_snapshot is not None else None,
        model_usage=usage_snapshot.model_usage if usage_snapshot is not None else None,
    )


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


def _event_agent_run_id(events: Sequence[Mapping[str, Any]], fallback: str) -> str:
    for event in events:
        if event.get("type") == "run.started":
            agent_run_id = event.get("agentRunId")
            if isinstance(agent_run_id, str):
                return agent_run_id

    return fallback


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
    if result.usage is not None and result.model_usage is not None:
        record["usage"] = result.usage
        record["modelUsage"] = result.model_usage

    return record


def _final_usage_snapshot(
    events: Sequence[Mapping[str, Any]],
) -> UsageSnapshot | None:
    for event in reversed(events):
        if event.get("type") != "usage.snapshot":
            continue

        usage = event.get("usage")
        model_usage = event.get("modelUsage")
        if not isinstance(usage, Mapping) or not isinstance(model_usage, list):
            raise TypeError("usage.snapshot must include usage and modelUsage")

        return UsageSnapshot(
            usage=dict(cast(Mapping[str, int], usage)),
            model_usage=[_mapping_record(row, "modelUsage row") for row in model_usage],
        )

    return None


def _mapping_record(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")

    return dict(value)
