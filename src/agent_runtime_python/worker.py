"""Placeholder Agent Run worker entry point.

The full worker will validate Agent Run worker protocol commands, execute LangGraph runs, and emit
protocol-compliant NDJSON events. This scaffold keeps the repository installable and testable before
runtime behavior is implemented.
"""

from __future__ import annotations


def main() -> int:
    """Run the placeholder worker command."""

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
