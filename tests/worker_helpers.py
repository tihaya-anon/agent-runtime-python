"""Shared worker test helpers."""

import json
from typing import Any

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent_runtime_python.runtime.protocol import EVENT_VALIDATOR

VALID_START_COMMAND = (
    '{"version":1,'
    '"type":"run.start",'
    '"agentRunId":"ar_python_smoke",'
    '"input":{"message":"Explain closures."},'
    '"runtimeProfile":{'
    '"schemaVersion":1,'
    '"profileId":"runtime-development",'
    '"runtimePolicy":{'
    '"agentBehaviorVersion":{'
    '"policy":"development",'
    '"requireCompleteDimensions":false,'
    '"rejectUnresolvedDimensions":false,'
    '"allowIncompleteAdHocRuns":true,'
    '"incompleteAdHocRuns":{"comparable":false,"promotable":false}'
    "},"
    '"sourceRevision":{"requireCleanForPublishedGraphVersions":false}'
    "}"
    "},"
    '"behaviorVersion":{"graph":"graph:python-smoke"}'
    "}\n"
)


def start_command_for_graph(graph_id: str) -> str:
    command = json.loads(VALID_START_COMMAND)
    command["behaviorVersion"]["graph"] = graph_id
    return json.dumps(command) + "\n"


def decode_events(output: str) -> list[dict[str, Any]]:
    events = [json.loads(line) for line in output.splitlines()]
    for event in events:
        EVENT_VALIDATOR.validate(event)

    return events


def tracer_provider(exporter: InMemorySpanExporter) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider
