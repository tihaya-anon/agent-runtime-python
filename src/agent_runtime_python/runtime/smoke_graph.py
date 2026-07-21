"""Minimal LangGraph graph used for worker smoke execution."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from agent_runtime_python.observability.telemetry import AgentRunTelemetry

SMOKE_GRAPH_ID = "graph:python-smoke"
SMOKE_GRAPH_NODE = "draft_response"


class SmokeGraphState(TypedDict):
    message: str
    response: str


def _draft_response_node(
    telemetry: AgentRunTelemetry | None,
) -> Callable[[SmokeGraphState], SmokeGraphState]:
    def draft_response(state: SmokeGraphState) -> SmokeGraphState:
        with _optional_node_span(telemetry):
            return {
                "message": state["message"],
                "response": f"Smoke graph received: {state['message']}",
            }

    return draft_response


def create_smoke_graph(telemetry: AgentRunTelemetry | None = None):
    graph = StateGraph(SmokeGraphState)
    graph.add_node(SMOKE_GRAPH_NODE, cast(Any, _draft_response_node(telemetry)))
    graph.add_edge(START, SMOKE_GRAPH_NODE)
    graph.add_edge(SMOKE_GRAPH_NODE, END)
    return graph.compile()


def run_smoke_graph(
    message: str,
    telemetry: AgentRunTelemetry | None = None,
) -> str:
    with _optional_graph_span(telemetry):
        result = create_smoke_graph(telemetry).invoke(
            {"message": message, "response": ""}
        )
    response = result["response"]
    if not isinstance(response, str):
        raise TypeError("Smoke graph response must be text")

    return response


def _optional_graph_span(
    telemetry: AgentRunTelemetry | None,
) -> AbstractContextManager[object]:
    if telemetry is None:
        return nullcontext()

    return telemetry.start_graph(SMOKE_GRAPH_ID)


def _optional_node_span(
    telemetry: AgentRunTelemetry | None,
) -> AbstractContextManager[object]:
    if telemetry is None:
        return nullcontext()

    return telemetry.start_graph_node(SMOKE_GRAPH_ID, SMOKE_GRAPH_NODE)
