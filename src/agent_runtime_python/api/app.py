"""FastAPI app factory for the internal Agent Run runtime API."""

from fastapi import FastAPI

from agent_runtime_python.api.middleware import RequestLoggingMiddleware
from agent_runtime_python.api.routes import router
from agent_runtime_python.api.runtime import NDJSON_CONTENT_TYPE, RuntimeApi
from agent_runtime_python.observability.logger import Logger, logger as default_logger
from agent_runtime_python.runtime.worker import AgentRunWorker

__all__ = ["NDJSON_CONTENT_TYPE", "create_app"]


def create_app(
    worker: AgentRunWorker | None = None,
    logger: Logger = default_logger,
) -> FastAPI:
    app = FastAPI(title="Agent Runtime Python", version="0.1.0")
    app.state.runtime_api = RuntimeApi(worker or AgentRunWorker())
    app.add_middleware(RequestLoggingMiddleware, logger=logger)
    app.include_router(router)

    return app
