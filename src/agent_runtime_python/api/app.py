"""FastAPI app for the internal Agent Run runtime API."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, Request, Response

from agent_runtime_python.protocol import PROTOCOL_VERSION, encode_event_line
from agent_runtime_python.worker import AgentRunWorker

INTERNAL_AGENT_RUNS_PATH = "/internal/agent-runs"
NDJSON_CONTENT_TYPE = "application/x-ndjson"
JSON_CONTENT_TYPE = "application/json"


def create_app(worker: AgentRunWorker | None = None) -> FastAPI:
    runtime = RuntimeApi(worker or AgentRunWorker())
    app = FastAPI(title="Agent Runtime Python", version="0.1.0")

    @app.middleware("http")
    async def log_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        body = await request.body()
        response = await call_next(request)
        log_request(request, response, body)
        return response

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(INTERNAL_AGENT_RUNS_PATH)
    async def start_run(request: Request) -> Response:
        return runtime.start_run(await request.body())

    @app.post(f"{INTERNAL_AGENT_RUNS_PATH}/{{agent_run_id}}/cancel")
    async def cancel_run(agent_run_id: str) -> Response:
        return runtime.cancel_run(agent_run_id)

    return app


class RuntimeApi:
    def __init__(self, worker: AgentRunWorker) -> None:
        self._worker = worker

    def start_run(self, body: bytes) -> Response:
        line = body.decode("utf-8", errors="replace")
        if not line.endswith("\n"):
            line = f"{line}\n"

        return worker_event_response(self._worker.handle_line(line))

    def cancel_run(self, agent_run_id: str) -> Response:
        command = (
            f'{{"version":{PROTOCOL_VERSION},'
            f'"type":"run.cancel",'
            f'"agentRunId":"{json_string_fragment(agent_run_id)}"}}\n'
        )
        return worker_event_response(self._worker.handle_line(command))


def worker_event_response(events: Sequence[dict[str, Any]]) -> Response:
    return Response(
        content="".join(encode_event_line(event) for event in events),
        media_type=NDJSON_CONTENT_TYPE,
    )


def json_string_fragment(value: str) -> str:
    return json.dumps(value)[1:-1]


def log_request(request: Request, response: Response, body: bytes) -> None:
    payload = {
        "message": "internal_api.request",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
    }
    agent_run_id = request_agent_run_id(request, body)
    if agent_run_id is not None:
        payload["agent_run_id"] = agent_run_id

    logging.info(json.dumps(payload, separators=(",", ":")))


def request_agent_run_id(request: Request, body: bytes) -> str | None:
    if request.url.path.startswith(f"{INTERNAL_AGENT_RUNS_PATH}/"):
        return cancel_agent_run_id(request.url.path)

    if request.url.path == INTERNAL_AGENT_RUNS_PATH:
        return command_agent_run_id(body)

    return None


def cancel_agent_run_id(path: str) -> str | None:
    cancel_prefix = f"{INTERNAL_AGENT_RUNS_PATH}/"
    if not path.endswith("/cancel"):
        return None

    return unquote(path[len(cancel_prefix) : -len("/cancel")])


def command_agent_run_id(body: bytes) -> str | None:
    try:
        command = json.loads(body)
    except json.JSONDecodeError:
        return None

    agent_run_id = command.get("agentRunId") if isinstance(command, dict) else None
    return agent_run_id if isinstance(agent_run_id, str) else None
