"""Experiment target adapters for local workers and HTTP Agent Run streams."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, cast
from urllib.request import Request, urlopen

from agent_runtime_python.experiments.serialization import (
    json_bytes,
    worker_command_line,
)
from agent_runtime_python.experiments.types import (
    ExperimentTarget,
    TargetKind,
    TargetRun,
    TrialPlan,
)
from agent_runtime_python.runtime.protocol import EVENT_VALIDATOR
from agent_runtime_python.runtime.worker import AgentRunWorker


class DirectWorkerTarget:
    def __init__(self, worker: AgentRunWorker | None = None) -> None:
        self._worker = worker or AgentRunWorker()

    def run(self, trial: TrialPlan) -> TargetRun:
        events = self._worker.handle_line(worker_command_line(trial.command))
        return worker_target_run(events, trial)


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
            data=json_bytes(trial.command),
            headers={
                "Accept": "application/x-ndjson",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        events = read_ndjson_worker_events(request, self._open_agent_run)
        return worker_target_run(events, trial)


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
            data=json_bytes(trial.command["input"]),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return TargetRun(
            events=read_ndjson_worker_events(request, self._open_agent_run),
            submitted_runtime_profile_id=None,
            submitted_behavior_version=None,
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


def worker_target_run(
    events: list[dict[str, Any]],
    trial: TrialPlan,
) -> TargetRun:
    return TargetRun(
        events=events,
        submitted_runtime_profile_id=command_runtime_profile_id(trial.command),
        submitted_behavior_version=command_behavior_version(trial.command),
    )


def command_runtime_profile_id(command: Mapping[str, Any]) -> str:
    runtime_profile = command["runtimeProfile"]
    if not isinstance(runtime_profile, Mapping):
        raise TypeError("runtimeProfile must be an object")

    return str(runtime_profile["profileId"])


def command_behavior_version(command: Mapping[str, Any]) -> dict[str, str]:
    behavior_version = command["behaviorVersion"]
    if not isinstance(behavior_version, Mapping):
        raise TypeError("behaviorVersion must be an object")

    return dict(cast(Mapping[str, str], behavior_version))


def read_ndjson_worker_events(
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
