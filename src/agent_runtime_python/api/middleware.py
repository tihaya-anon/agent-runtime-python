"""HTTP middleware for the internal Agent Run runtime API."""

from __future__ import annotations

from time import perf_counter

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from agent_runtime_python.api.routes import request_agent_run_id
from agent_runtime_python.observability.logger import Logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, logger: Logger) -> None:
        super().__init__(app)
        self._logger = logger

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        started_at = perf_counter()
        response = await call_next(request)
        log_request(request, response, perf_counter() - started_at, self._logger)
        return response


def log_request(
    request: Request,
    response: Response,
    duration_seconds: float,
    logger: Logger,
) -> None:
    attributes: dict[str, str | int | float] = {
        "http.request.method": request.method,
        "http.response.status_code": response.status_code,
        "url.path": request.url.path,
        "server.request.duration_ms": duration_seconds * 1000,
    }
    agent_run_id = request_agent_run_id(request)
    if agent_run_id is not None:
        attributes["agent_run_id"] = agent_run_id

    logger.info(
        "HTTP request completed",
        event_name="http.server.request.completed",
        attributes=attributes,
    )
