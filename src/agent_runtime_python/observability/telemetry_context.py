"""Context-local telemetry state for one Agent Run execution."""

from __future__ import annotations

from contextvars import ContextVar

from agent_runtime_python.observability.usage import UsageAccumulator

CURRENT_USAGE_ACCUMULATOR: ContextVar[UsageAccumulator | None] = ContextVar(
    "agent_runtime_usage_accumulator",
    default=None,
)
CURRENT_GRAPH_ID: ContextVar[str | None] = ContextVar(
    "agent_runtime_graph_id",
    default=None,
)
CURRENT_GRAPH_NODE_NAME: ContextVar[str | None] = ContextVar(
    "agent_runtime_graph_node_name",
    default=None,
)
