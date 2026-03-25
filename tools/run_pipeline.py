"""Compatibility wrapper for the new V2 backend pipelines."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from server.pipelines.orchestrator import run_full_pipeline  # noqa: E402
from server.repositories.db import init_db  # noqa: E402


def run_pipeline() -> dict:
    init_db()
    return run_full_pipeline(trigger_type="manual")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_pipeline(), indent=2))
