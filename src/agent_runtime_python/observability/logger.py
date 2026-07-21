"""Structured logging for the Agent Runtime Python service."""

from __future__ import annotations

import json
import logging
import os
import traceback
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol, TypeAlias

from opentelemetry import trace

DEFAULT_SERVICE_NAME = "agent-runtime-python"
LOG_LEVELS = ("trace", "debug", "info", "warn", "error", "fatal")
SEVERITY_NUMBERS = {
    "trace": 1,
    "debug": 5,
    "info": 9,
    "warn": 13,
    "error": 17,
    "fatal": 21,
}
PYTHON_LOG_LEVELS = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}

LogAttributeValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | list["LogAttributeValue"]
    | dict[str, "LogAttributeValue"]
)
LogAttributes: TypeAlias = Mapping[str, LogAttributeValue]


class Logger(Protocol):
    def debug(
        self,
        body: str,
        *,
        attributes: LogAttributes | None = None,
        error: BaseException | None = None,
        event_name: str | None = None,
    ) -> None: ...

    def info(
        self,
        body: str,
        *,
        attributes: LogAttributes | None = None,
        error: BaseException | None = None,
        event_name: str | None = None,
    ) -> None: ...

    def warning(
        self,
        body: str,
        *,
        attributes: LogAttributes | None = None,
        error: BaseException | None = None,
        event_name: str | None = None,
    ) -> None: ...

    def error(
        self,
        body: str,
        *,
        attributes: LogAttributes | None = None,
        error: BaseException | None = None,
        event_name: str | None = None,
    ) -> None: ...

    def child(self, attributes: LogAttributes) -> Logger: ...


class StructuredLogger:
    """Emit OpenTelemetry-shaped log records through a dedicated Python logger."""

    def __init__(
        self,
        *,
        service_name: str,
        service_version: str | None = None,
        environment_name: str | None = None,
        minimum_level: str = "info",
        attributes: LogAttributes | None = None,
        python_logger: logging.Logger | None = None,
    ) -> None:
        normalized_level = minimum_level.lower()
        if normalized_level not in LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(LOG_LEVELS)}")

        self._service_name = service_name
        self._service_version = service_version
        self._environment_name = environment_name
        self._minimum_level = normalized_level
        self._minimum_level_index = LOG_LEVELS.index(normalized_level)
        self._attributes = dict(attributes or {})
        self._logger = python_logger or logging.getLogger(DEFAULT_SERVICE_NAME)
        self._logger.setLevel(_python_level(normalized_level))

    def debug(
        self,
        body: str,
        *,
        attributes: LogAttributes | None = None,
        error: BaseException | None = None,
        event_name: str | None = None,
    ) -> None:
        self._write("debug", body, attributes, error, event_name)

    def info(
        self,
        body: str,
        *,
        attributes: LogAttributes | None = None,
        error: BaseException | None = None,
        event_name: str | None = None,
    ) -> None:
        self._write("info", body, attributes, error, event_name)

    def warning(
        self,
        body: str,
        *,
        attributes: LogAttributes | None = None,
        error: BaseException | None = None,
        event_name: str | None = None,
    ) -> None:
        self._write("warn", body, attributes, error, event_name)

    def error(
        self,
        body: str,
        *,
        attributes: LogAttributes | None = None,
        error: BaseException | None = None,
        event_name: str | None = None,
    ) -> None:
        self._write("error", body, attributes, error, event_name)

    def child(self, attributes: LogAttributes) -> Logger:
        return StructuredLogger(
            service_name=self._service_name,
            service_version=self._service_version,
            environment_name=self._environment_name,
            minimum_level=self._minimum_level,
            attributes={**self._attributes, **attributes},
            python_logger=self._logger,
        )

    def _write(
        self,
        level: str,
        body: str,
        attributes: LogAttributes | None,
        error: BaseException | None,
        event_name: str | None,
    ) -> None:
        if not self._should_log(level):
            return

        record = self._log_record(level, body, attributes, error, event_name)
        self._logger.log(
            _python_level(level), json.dumps(record, separators=(",", ":"))
        )

    def _should_log(self, level: str) -> bool:
        return LOG_LEVELS.index(level) >= self._minimum_level_index

    def _log_record(
        self,
        level: str,
        body: str,
        attributes: LogAttributes | None,
        error: BaseException | None,
        event_name: str | None,
    ) -> dict[str, LogAttributeValue]:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        merged_attributes: dict[str, LogAttributeValue] = {
            **self._attributes,
            **dict(attributes or {}),
        }
        if error is not None:
            merged_attributes.update(_serialize_error(error))

        record: dict[str, LogAttributeValue] = {
            "timestamp": now,
            "observedTimestamp": now,
            "severityNumber": SEVERITY_NUMBERS[level],
            "severityText": level.upper(),
            "body": body,
            "resource": self._resource_attributes(),
            "attributes": merged_attributes,
        }
        if event_name is not None:
            record["eventName"] = event_name

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            record["traceId"] = f"{span_context.trace_id:032x}"
            record["spanId"] = f"{span_context.span_id:016x}"
            record["traceFlags"] = int(span_context.trace_flags)

        return record

    def _resource_attributes(self) -> dict[str, LogAttributeValue]:
        resource: dict[str, LogAttributeValue] = {
            "service.name": self._service_name,
        }
        if self._service_version is not None:
            resource["service.version"] = self._service_version
        if self._environment_name is not None:
            resource["deployment.environment.name"] = self._environment_name

        return resource


def create_logger_from_environment(
    *,
    default_service_name: str = DEFAULT_SERVICE_NAME,
) -> Logger:
    return StructuredLogger(
        service_name=os.getenv("OTEL_SERVICE_NAME", default_service_name),
        service_version=os.getenv("AGENT_RUNTIME_PYTHON_VERSION"),
        environment_name=os.getenv("ENVIRONMENT") or os.getenv("NODE_ENV"),
        minimum_level=os.getenv("LOG_LEVEL", "info"),
    )


def _python_level(level: str) -> int:
    return PYTHON_LOG_LEVELS[level]


def _serialize_error(error: BaseException) -> dict[str, LogAttributeValue]:
    return {
        "exception.type": error.__class__.__name__,
        "exception.message": str(error),
        "exception.stacktrace": "".join(
            traceback.format_exception(type(error), error, error.__traceback__),
        ),
    }


logger = create_logger_from_environment()
