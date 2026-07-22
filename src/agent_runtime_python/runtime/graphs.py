"""Runtime graph registry for Agent Run worker execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from agent_runtime_python.observability.telemetry import AgentRunTelemetry
from agent_runtime_python.runtime.smoke_graph import (
    SMOKE_GRAPH_ID,
    SMOKE_USAGE_FAILURE_GRAPH_ID,
    SMOKE_USAGE_GRAPH_ID,
    run_smoke_graph,
    run_smoke_usage_failure_graph,
    run_smoke_usage_graph,
)

GraphRunner = Callable[[str, AgentRunTelemetry | None], str]


class UnsupportedGraphError(ValueError):
    """Raised when a worker command requests an unknown runtime graph."""


GRAPH_REGISTRY: Mapping[str, GraphRunner] = {
    SMOKE_GRAPH_ID: run_smoke_graph,
    SMOKE_USAGE_GRAPH_ID: run_smoke_usage_graph,
    SMOKE_USAGE_FAILURE_GRAPH_ID: run_smoke_usage_failure_graph,
}


def run_registered_graph(
    graph_id: str,
    message: str,
    telemetry: AgentRunTelemetry | None = None,
) -> str:
    runner = GRAPH_REGISTRY.get(graph_id)
    if runner is None:
        raise UnsupportedGraphError(f"Unsupported graph id: {graph_id}")

    return runner(message, telemetry)
