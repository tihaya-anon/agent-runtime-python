"""Internal HTTP adapter for Agent Run worker commands."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

from agent_runtime_python.protocol import PROTOCOL_VERSION, encode_event_line
from agent_runtime_python.worker import AgentRunWorker

INTERNAL_AGENT_RUNS_PATH = "/internal/agent-runs"
NDJSON_CONTENT_TYPE = "application/x-ndjson"
JSON_CONTENT_TYPE = "application/json"


@dataclass(frozen=True)
class InternalApiResponse:
    status: int
    content_type: str
    body: bytes


def handle_internal_request(
    method: str,
    path: str,
    body: bytes,
    worker: AgentRunWorker | None = None,
) -> InternalApiResponse:
    """Handle one internal runtime request without binding to a socket."""

    active_worker = worker or AgentRunWorker()
    parsed_path = urlparse(path).path
    if method != "POST":
        return _json_response(405, {"error": "method_not_allowed"})

    if parsed_path == INTERNAL_AGENT_RUNS_PATH:
        line = body.decode("utf-8", errors="replace")
        if not line.endswith("\n"):
            line = f"{line}\n"
        return _worker_event_response(active_worker.handle_line(line))

    cancel_prefix = f"{INTERNAL_AGENT_RUNS_PATH}/"
    if parsed_path.endswith("/cancel") and parsed_path.startswith(cancel_prefix):
        agent_run_id = unquote(parsed_path[len(cancel_prefix) : -len("/cancel")])
        command = (
            f'{{"version":{PROTOCOL_VERSION},'
            f'"type":"run.cancel",'
            f'"agentRunId":"{_json_string_fragment(agent_run_id)}"}}\n'
        )
        return _worker_event_response(active_worker.handle_line(command))

    return _json_response(404, {"error": "not_found"})


class InternalApiHandler(BaseHTTPRequestHandler):
    worker = AgentRunWorker()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        response = handle_internal_request(
            "POST",
            self.path,
            body,
            self.worker,
        )
        self._send_response(response)

    def do_GET(self) -> None:
        self._send_response(_json_response(405, {"error": "method_not_allowed"}))

    def log_message(self, format: str, *args: Any) -> None:
        return None

    def _send_response(self, response: InternalApiResponse) -> None:
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)


def run_internal_api_server(host: str = "127.0.0.1", port: int = 8088) -> None:
    server = ThreadingHTTPServer((host, port), InternalApiHandler)
    server.serve_forever()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the internal Agent Run API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args(argv)

    run_internal_api_server(args.host, args.port)
    return 0


def _worker_event_response(events: Sequence[dict[str, Any]]) -> InternalApiResponse:
    body = "".join(encode_event_line(event) for event in events).encode("utf-8")
    return InternalApiResponse(
        status=200,
        content_type=NDJSON_CONTENT_TYPE,
        body=body,
    )


def _json_response(status: int, payload: dict[str, str]) -> InternalApiResponse:
    import json

    return InternalApiResponse(
        status=status,
        content_type=JSON_CONTENT_TYPE,
        body=f"{json.dumps(payload, separators=(',', ':'))}\n".encode("utf-8"),
    )


def _json_string_fragment(value: str) -> str:
    import json

    return json.dumps(value)[1:-1]


if __name__ == "__main__":
    raise SystemExit(main())
