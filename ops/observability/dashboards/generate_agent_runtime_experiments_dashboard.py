"""Generate the Agent Runtime Experiments Grafana dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from dashboard_builder import build_dashboard

DASHBOARD_PATH = Path(__file__).with_name("agent-runtime-experiments.dashboard.json")


def main() -> int:
    dashboard = build_dashboard()
    DASHBOARD_PATH.write_text(
        f"{json.dumps(dashboard, separators=(',', ':'), sort_keys=True)}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
