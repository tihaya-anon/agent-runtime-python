"""Minimal LangGraph graph used for worker smoke execution."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from agent_runtime_python.observability.usage import ProviderUsage
from agent_runtime_python.observability.telemetry import AgentRunTelemetry

SMOKE_GRAPH_ID = "graph:python-smoke"
SMOKE_USAGE_GRAPH_ID = "graph:python-smoke-usage"
SMOKE_USAGE_FAILURE_GRAPH_ID = "graph:python-smoke-usage-failure"
SMOKE_GRAPH_NODE = "draft_response"
SMOKE_PROVIDER = "synthetic"
SMOKE_MODEL = "model:deterministic-smoke"
SMOKE_PROVIDER_USAGE = ProviderUsage(
    input_tokens=11,
    output_tokens=7,
    total_tokens=18,
    cached_input_tokens=3,
    cache_creation_input_tokens=2,
    reasoning_output_tokens=1,
)


class SmokeGraphState(TypedDict):
    message: str
    response: str


def _draft_response_node(
    telemetry: AgentRunTelemetry | None,
    graph_id: str,
    observe_model_usage: bool,
    fail_after_usage: bool,
) -> Callable[[SmokeGraphState], SmokeGraphState]:
    def draft_response(state: SmokeGraphState) -> SmokeGraphState:
        with _optional_node_span(telemetry, graph_id):
            response = f"Smoke graph received: {state['message']}"
            if observe_model_usage and telemetry is not None:
                with telemetry.start_model_call(
                    provider=SMOKE_PROVIDER,
                    model=SMOKE_MODEL,
                    usage=SMOKE_PROVIDER_USAGE,
                    provider_finish_reason="stop",
                    finish_reason="stop",
                ):
                    response = f"Smoke graph received: {state['message']}"
            if fail_after_usage:
                raise RuntimeError("Synthetic smoke graph failure after model usage")

            return {
                "message": state["message"],
                "response": response,
            }

    return draft_response


def create_smoke_graph(
    telemetry: AgentRunTelemetry | None = None,
    graph_id: str = SMOKE_GRAPH_ID,
    observe_model_usage: bool = False,
    fail_after_usage: bool = False,
):
    graph = StateGraph(SmokeGraphState)
    graph.add_node(
        SMOKE_GRAPH_NODE,
        cast(
            Any,
            _draft_response_node(
                telemetry,
                graph_id,
                observe_model_usage,
                fail_after_usage,
            ),
        ),
    )
    graph.add_edge(START, SMOKE_GRAPH_NODE)
    graph.add_edge(SMOKE_GRAPH_NODE, END)
    return graph.compile()


def run_smoke_graph(
    message: str,
    telemetry: AgentRunTelemetry | None = None,
) -> str:
    return _run_smoke_graph(
        message,
        telemetry,
        graph_id=SMOKE_GRAPH_ID,
        observe_model_usage=False,
        fail_after_usage=False,
    )


def run_smoke_usage_graph(
    message: str,
    telemetry: AgentRunTelemetry | None = None,
) -> str:
    return _run_smoke_graph(
        message,
        telemetry,
        graph_id=SMOKE_USAGE_GRAPH_ID,
        observe_model_usage=True,
        fail_after_usage=False,
    )


def run_smoke_usage_failure_graph(
    message: str,
    telemetry: AgentRunTelemetry | None = None,
) -> str:
    return _run_smoke_graph(
        message,
        telemetry,
        graph_id=SMOKE_USAGE_FAILURE_GRAPH_ID,
        observe_model_usage=True,
        fail_after_usage=True,
    )


def _run_smoke_graph(
    message: str,
    telemetry: AgentRunTelemetry | None,
    *,
    graph_id: str,
    observe_model_usage: bool,
    fail_after_usage: bool,
) -> str:
    with _optional_graph_span(telemetry, graph_id):
        result = create_smoke_graph(
            telemetry,
            graph_id=graph_id,
            observe_model_usage=observe_model_usage,
            fail_after_usage=fail_after_usage,
        ).invoke({"message": message, "response": ""})
    response = result["response"]
    if not isinstance(response, str):
        raise TypeError("Smoke graph response must be text")

    return response


def _optional_graph_span(
    telemetry: AgentRunTelemetry | None,
    graph_id: str,
) -> AbstractContextManager[object]:
    if telemetry is None:
        return nullcontext()

    return telemetry.start_graph(graph_id)


def _optional_node_span(
    telemetry: AgentRunTelemetry | None,
    graph_id: str,
) -> AbstractContextManager[object]:
    if telemetry is None:
        return nullcontext()

    return telemetry.start_graph_node(graph_id, SMOKE_GRAPH_NODE)
