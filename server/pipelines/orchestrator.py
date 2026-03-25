"""Top-level orchestration for the V2 backend."""

from __future__ import annotations

from datetime import datetime, timezone

from server.pipelines.discovery_pipeline import run_discovery_pipeline
from server.pipelines.status_pipeline import run_status_pipeline
from server.services.synthesis import ensure_synthesis


def run_full_pipeline(trigger_type: str = "manual") -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    status_stats = run_status_pipeline(trigger_type=trigger_type)
    discovery_stats = run_discovery_pipeline(trigger_type=trigger_type)
    trend, signals = ensure_synthesis()
    completed_at = datetime.now(timezone.utc).isoformat()
    return {
        "started_at": started_at,
        "completed_at": completed_at,
        "status": status_stats,
        "discovery": discovery_stats,
        "synthesis": {
            "trend_ready": bool(trend),
            "signals_ready": len(signals),
        },
    }
