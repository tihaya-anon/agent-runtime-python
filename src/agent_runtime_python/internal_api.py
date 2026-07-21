"""Internal HTTP API entry point."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

import uvicorn

from agent_runtime_python.api import create_app
from agent_runtime_python.observability.telemetry import (
    configure_telemetry_from_environment,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the internal Agent Run API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    configure_telemetry_from_environment()
    uvicorn.run(create_app(), host=args.host, port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
