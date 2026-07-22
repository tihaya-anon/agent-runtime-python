"""Agent Run worker entry point."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import Any, TextIO

from agent_runtime_python.observability.telemetry import (
    AgentRunTelemetry,
    configure_telemetry_from_environment,
)
from agent_runtime_python.runtime.graphs import (
    UnsupportedGraphError,
    run_registered_graph,
)
from agent_runtime_python.runtime.protocol import (
    PROTOCOL_VERSION,
    ProtocolValidationError,
    encode_event_line,
    parse_command_line,
    validation_failure_event,
)

WorkerEvent = dict[str, Any]


class AgentRunWorker:
    """Executes one-command-at-a-time Agent Run worker protocol messages."""

    def __init__(self, telemetry: AgentRunTelemetry | None = None) -> None:
        self._telemetry = telemetry or AgentRunTelemetry()

    def handle_line(self, line: str) -> list[WorkerEvent]:
        try:
            command = parse_command_line(line)
        except ProtocolValidationError:
            return [validation_failure_event()]

        if command["type"] == "run.cancel":
            return [_run_cancelled_event()]

        with self._telemetry.start_run(command) as span:
            events = self._run_agent(command)
            events = self._with_usage_snapshot(events)
            self._telemetry.finish_run(span, events[-1])
            return events

    def _run_agent(self, command: dict[str, Any]) -> list[WorkerEvent]:
        agent_run_id = command["agentRunId"]
        message = command["input"]["message"]
        graph_id = command["behaviorVersion"]["graph"]
        events = _started_run_events(agent_run_id, graph_id)

        try:
            response = run_registered_graph(graph_id, message, self._telemetry)
        except UnsupportedGraphError:
            return _failed_run_events(events, graph_id, "validation")
        except Exception:
            return _failed_run_events(events, graph_id, "internal")

        return _completed_run_events(events, graph_id, response)

    def _with_usage_snapshot(self, events: list[WorkerEvent]) -> list[WorkerEvent]:
        usage_snapshot = self._telemetry.usage_snapshot_event()
        if usage_snapshot is None:
            return events

        return [*events[:-1], usage_snapshot, events[-1]]


def _started_run_events(agent_run_id: str, graph_id: str) -> list[WorkerEvent]:
    return [
        {
            "version": PROTOCOL_VERSION,
            "type": "run.started",
            "agentRunId": agent_run_id,
        },
        _progress_event(graph_id, "started"),
    ]


def _completed_run_events(
    started_events: list[WorkerEvent],
    graph_id: str,
    response: str,
) -> list[WorkerEvent]:
    return [
        *started_events,
        {"version": PROTOCOL_VERSION, "type": "message.delta", "text": response},
        _progress_event(graph_id, "completed"),
        {"version": PROTOCOL_VERSION, "type": "run.completed"},
    ]


def _failed_run_events(
    started_events: list[WorkerEvent],
    graph_id: str,
    error_classification: str,
) -> list[WorkerEvent]:
    return [
        *started_events,
        _progress_event(graph_id, "failed"),
        {
            "version": PROTOCOL_VERSION,
            "type": "run.failed",
            "errorClassification": error_classification,
        },
    ]


def _progress_event(graph_id: str, status: str) -> WorkerEvent:
    return {
        "version": PROTOCOL_VERSION,
        "type": "progress.update",
        "scope": "run",
        "label": graph_id,
        "status": status,
    }


def _run_cancelled_event() -> WorkerEvent:
    return {"version": PROTOCOL_VERSION, "type": "run.cancelled"}


def run_worker(
    input_stream: Iterable[str],
    output_stream: TextIO,
    worker: AgentRunWorker | None = None,
) -> None:
    active_worker = worker or AgentRunWorker()

    for line in input_stream:
        for event in active_worker.handle_line(line):
            output_stream.write(encode_event_line(event))
            output_stream.flush()


def main(
    input_stream: Iterable[str] | None = None, output_stream: TextIO | None = None
) -> int:
    """Run the worker over stdin/stdout NDJSON."""

    configure_telemetry_from_environment()
    run_worker(input_stream or sys.stdin, output_stream or sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
