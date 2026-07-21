"""Compatibility exports for the runtime worker."""

from agent_runtime_python.runtime.worker import *  # noqa: F403
from agent_runtime_python.runtime.worker import main

if __name__ == "__main__":
    raise SystemExit(main())
