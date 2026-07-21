"""Adapter between HTTP API models and runtime worker commands."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import Response

from agent_runtime_python.api.models import StartRunCommand
from agent_runtime_python.runtime.protocol import PROTOCOL_VERSION, encode_event_line
from agent_runtime_python.runtime.worker import AgentRunWorker

NDJSON_CONTENT_TYPE = "application/x-ndjson"


class RuntimeApi:
    def __init__(self, worker: AgentRunWorker) -> None:
        self._worker = worker

    def start_run(self, command: StartRunCommand) -> Response:
        return self._handle_command(command.to_worker_command())

    def cancel_run(self, agent_run_id: str) -> Response:
        return self._handle_command(cancel_run_command(agent_run_id))

    def _handle_command(self, command: Mapping[str, Any]) -> Response:
        return worker_event_response(
            self._worker.handle_line(worker_command_line(command))
        )


def worker_event_response(events: Sequence[dict[str, Any]]) -> Response:
    return Response(
        content="".join(encode_event_line(event) for event in events),
        media_type=NDJSON_CONTENT_TYPE,
    )


def worker_command_line(command: Mapping[str, Any]) -> str:
    return f"{json.dumps(command, separators=(',', ':'))}\n"


def cancel_run_command(agent_run_id: str) -> dict[str, str | int]:
    return {
        "version": PROTOCOL_VERSION,
        "type": "run.cancel",
        "agentRunId": agent_run_id,
    }
