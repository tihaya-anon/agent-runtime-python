"""Routes for the internal Agent Run runtime API."""

from __future__ import annotations

import json
from urllib.parse import unquote

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from agent_runtime_python.api.models import StartRunCommand
from agent_runtime_python.api.runtime import RuntimeApi

INTERNAL_AGENT_RUNS_PATH = "/internal/agent-runs"

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post(INTERNAL_AGENT_RUNS_PATH)
async def start_run(request: Request) -> Response:
    command = await start_run_command_from_request(request)
    request.state.agent_run_id = command.agent_run_id
    return runtime_api(request).start_run(command)


@router.post(f"{INTERNAL_AGENT_RUNS_PATH}/{{agent_run_id}}/cancel")
async def cancel_run(request: Request, agent_run_id: str) -> Response:
    request.state.agent_run_id = agent_run_id
    return runtime_api(request).cancel_run(agent_run_id)


async def start_run_command_from_request(request: Request) -> StartRunCommand:
    try:
        body = await request.json()
    except json.JSONDecodeError as error:
        raise RequestValidationError(
            [{"type": "json_invalid", "loc": ("body",), "msg": str(error)}],
        ) from error

    try:
        return StartRunCommand.model_validate(body)
    except ValidationError as error:
        raise RequestValidationError(errors=error.errors()) from error


def runtime_api(request: Request) -> RuntimeApi:
    api = request.app.state.runtime_api
    if not isinstance(api, RuntimeApi):
        raise RuntimeError("Runtime API is not configured")

    return api


def request_agent_run_id(request: Request) -> str | None:
    state_agent_run_id = getattr(request.state, "agent_run_id", None)
    if isinstance(state_agent_run_id, str):
        return state_agent_run_id

    if request.url.path.startswith(f"{INTERNAL_AGENT_RUNS_PATH}/"):
        return cancel_agent_run_id(request.url.path)

    return None


def cancel_agent_run_id(path: str) -> str | None:
    cancel_prefix = f"{INTERNAL_AGENT_RUNS_PATH}/"
    if not path.endswith("/cancel"):
        return None

    return unquote(path[len(cancel_prefix) : -len("/cancel")])
