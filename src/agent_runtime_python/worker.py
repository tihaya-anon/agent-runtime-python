"""Agent Run worker entry point."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import Any, TextIO

from agent_runtime_python.graphs import UnsupportedGraphError, run_registered_graph
from agent_runtime_python.protocol import (
    PROTOCOL_VERSION,
    ProtocolValidationError,
    encode_event_line,
    parse_command_line,
    validation_failure_event,
)
from agent_runtime_python.telemetry import (
    AgentRunTelemetry,
    configure_telemetry_from_environment,
)


class AgentRunWorker:
    """Executes one-command-at-a-time Agent Run worker protocol messages."""

    def __init__(self, telemetry: AgentRunTelemetry | None = None) -> None:
        self._telemetry = telemetry or AgentRunTelemetry()

    def handle_line(self, line: str) -> list[dict[str, Any]]:
        try:
            command = parse_command_line(line)
        except ProtocolValidationError:
            return [validation_failure_event()]

        if command["type"] == "run.cancel":
            return [{"version": PROTOCOL_VERSION, "type": "run.cancelled"}]

        with self._telemetry.start_run(command) as span:
            events = self._run_agent(command)
            self._telemetry.finish_run(span, events[-1])
            return events

    def _run_agent(self, command: dict[str, Any]) -> list[dict[str, Any]]:
        agent_run_id = command["agentRunId"]
        message = command["input"]["message"]
        graph_id = command["behaviorVersion"]["graph"]
        events = [
            {
                "version": PROTOCOL_VERSION,
                "type": "run.started",
                "agentRunId": agent_run_id,
            },
            {
                "version": PROTOCOL_VERSION,
                "type": "progress.update",
                "scope": "run",
                "label": graph_id,
                "status": "started",
            },
        ]

        try:
            response = run_registered_graph(graph_id, message, self._telemetry)
        except UnsupportedGraphError:
            return [
                *events,
                {
                    "version": PROTOCOL_VERSION,
                    "type": "progress.update",
                    "scope": "run",
                    "label": graph_id,
                    "status": "failed",
                },
                {
                    "version": PROTOCOL_VERSION,
                    "type": "run.failed",
                    "errorClassification": "validation",
                },
            ]
        except Exception:
            return [
                *events,
                {
                    "version": PROTOCOL_VERSION,
                    "type": "progress.update",
                    "scope": "run",
                    "label": graph_id,
                    "status": "failed",
                },
                {
                    "version": PROTOCOL_VERSION,
                    "type": "run.failed",
                    "errorClassification": "internal",
                },
            ]

        return [
            *events,
            {"version": PROTOCOL_VERSION, "type": "message.delta", "text": response},
            {
                "version": PROTOCOL_VERSION,
                "type": "progress.update",
                "scope": "run",
                "label": graph_id,
                "status": "completed",
            },
            {"version": PROTOCOL_VERSION, "type": "run.completed"},
        ]


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
