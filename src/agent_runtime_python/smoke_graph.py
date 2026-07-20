"""Minimal LangGraph graph used for worker smoke execution."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class SmokeGraphState(TypedDict):
    message: str
    response: str


def _draft_response(state: SmokeGraphState) -> SmokeGraphState:
    return {
        "message": state["message"],
        "response": f"Smoke graph received: {state['message']}",
    }


def create_smoke_graph():
    graph = StateGraph(SmokeGraphState)
    graph.add_node("draft_response", _draft_response)
    graph.add_edge(START, "draft_response")
    graph.add_edge("draft_response", END)
    return graph.compile()


def run_smoke_graph(message: str) -> str:
    result = create_smoke_graph().invoke({"message": message, "response": ""})
    response = result["response"]
    if not isinstance(response, str):
        raise TypeError("Smoke graph response must be text")

    return response
