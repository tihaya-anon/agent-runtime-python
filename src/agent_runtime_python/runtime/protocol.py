"""Agent Run worker protocol validation and encoding."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

PROTOCOL_VERSION = 1


class ProtocolValidationError(ValueError):
    """Raised when an Agent Run worker protocol message is malformed."""


def _load_schema(schema_file_name: str) -> dict[str, Any]:
    schema = (
        files("agent_runtime_python.schemas").joinpath(schema_file_name).read_text()
    )
    parsed_schema = json.loads(schema)
    if not isinstance(parsed_schema, dict):
        raise TypeError(f"{schema_file_name} must contain one JSON Schema object")

    return parsed_schema


COMMAND_VALIDATOR = Draft202012Validator(
    _load_schema("agent-run-worker-command.schema.json"),
)
EVENT_VALIDATOR = Draft202012Validator(
    _load_schema("agent-run-worker-event.schema.json"),
)


def parse_command_line(line: str) -> dict[str, Any]:
    """Parse and validate one NDJSON command line."""

    record = line.removesuffix("\n").removesuffix("\r")
    if not record or "\n" in record or "\r" in record:
        raise ProtocolValidationError(
            "Worker command must be one non-empty NDJSON record"
        )

    try:
        command = json.loads(record)
    except json.JSONDecodeError as error:
        raise ProtocolValidationError("Worker command must be valid JSON") from error

    try:
        COMMAND_VALIDATOR.validate(command)
        _validate_command_invariants(command)
    except ValidationError as error:
        raise ProtocolValidationError("Worker command violates schema") from error

    if not isinstance(command, dict):
        raise ProtocolValidationError("Worker command must be a JSON object")

    return command


def encode_event_line(event: dict[str, Any]) -> str:
    """Validate and encode one NDJSON worker event line."""

    EVENT_VALIDATOR.validate(event)
    return f"{json.dumps(event, separators=(',', ':'))}\n"


def validation_failure_event() -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "type": "run.failed",
        "errorClassification": "validation",
    }


def _validate_command_invariants(command: Any) -> None:
    if not isinstance(command, dict):
        raise ProtocolValidationError("Worker command must be a JSON object")

    agent_run_id = command.get("agentRunId")
    if not isinstance(agent_run_id, str) or not agent_run_id.strip():
        raise ProtocolValidationError("agentRunId must not be empty")

    if command.get("type") != "run.start":
        return

    input_message = command.get("input", {}).get("message")
    if not isinstance(input_message, str) or not input_message.strip():
        raise ProtocolValidationError("input.message must not be empty")
