"""Environment-driven OpenTelemetry SDK configuration."""

from __future__ import annotations

import os

from opentelemetry import trace

from agent_runtime_python.observability.telemetry.attributes import SERVICE_NAME

_TELEMETRY_CONFIGURED = False


def configure_telemetry_from_environment() -> None:
    """Configure OTLP trace export when standard OpenTelemetry env vars request it."""

    global _TELEMETRY_CONFIGURED
    if _TELEMETRY_CONFIGURED or not _otel_export_enabled():
        return

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", SERVICE_NAME),
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _TELEMETRY_CONFIGURED = True


def _otel_export_enabled() -> bool:
    if os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        return False

    traces_exporter = os.getenv("OTEL_TRACES_EXPORTER", "").lower()
    if traces_exporter in {"none", "console"}:
        return False

    return bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or traces_exporter)
