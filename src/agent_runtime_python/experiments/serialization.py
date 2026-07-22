"""JSON and text helpers shared by experiment internals."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent_runtime_python.experiments.types import JsonScalar


def stable_json(value: Mapping[str, JsonScalar]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def stable_json_record(value: Mapping[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def worker_command_line(command: Mapping[str, Any]) -> str:
    return f"{json.dumps(command, separators=(',', ':'))}\n"


def summarize_response(response_text: str, limit: int = 240) -> str:
    normalized = " ".join(response_text.split())
    if len(normalized) <= limit:
        return normalized

    return normalized[: limit - 1].rstrip() + "..."


def optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def identifier_token(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def parse_parameter_matrix(entries: Sequence[str]) -> dict[str, list[JsonScalar]]:
    if not entries:
        return {"promptStyle": ["concise", "detailed"]}

    matrix = {}
    for entry in entries:
        name, raw_values = split_key_value_entry(entry)
        values = [_parse_json_scalar(value) for value in raw_values.split(",") if value]
        if not values:
            raise ValueError(f"Parameter {name} must include at least one value")
        matrix[name] = values

    return matrix


def parse_key_value_entries(entries: Sequence[str]) -> dict[str, str]:
    return dict(split_key_value_entry(entry) for entry in entries)


def split_key_value_entry(entry: str) -> tuple[str, str]:
    if "=" not in entry:
        raise ValueError(f"Expected name=value entry, received {entry!r}")

    name, value = entry.split("=", 1)
    if not name.strip():
        raise ValueError(f"Expected non-empty name in {entry!r}")

    return name, value


def _parse_json_scalar(value: str) -> JsonScalar:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value

    if isinstance(parsed, str | int | float | bool):
        return parsed

    raise ValueError(
        f"Parameter values must be strings, numbers, or booleans: {value!r}"
    )
