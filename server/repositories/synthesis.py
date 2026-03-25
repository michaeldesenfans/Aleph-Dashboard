"""Repository for synthesis outputs."""

from __future__ import annotations

import json

from server.repositories.db import get_conn


def save_trend(trend: dict) -> int:
    conn = get_conn()
    cur = conn.execute(
        """
        INSERT INTO trend_snapshots
            (title, narrative, confidence, impact_level, window_start, window_end, evidence_event_ids, model_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trend["title"],
            trend["narrative"],
            _normalize_confidence(trend.get("confidence", 0.5)),
            trend.get("impact_level", "medium"),
            trend.get("window_start"),
            trend.get("window_end"),
            json.dumps(trend.get("evidence_event_ids", [])),
            trend.get("model_version", "heuristic"),
        ),
    )
    conn.commit()
    trend_id = cur.lastrowid
    conn.close()
    return trend_id


def get_latest_trend():
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM trend_snapshots ORDER BY generated_at DESC, id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


_CONF_MAP = {"critical": 0.95, "high": 0.85, "medium": 0.65, "low": 0.45}


def _normalize_confidence(raw) -> float:
    if isinstance(raw, str):
        return _CONF_MAP.get(raw.lower(), 0.7)
    try:
        return min(max(float(raw), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.5


def replace_signals(signals: list[dict]):
    conn = get_conn()
    conn.execute("DELETE FROM strategic_signals")
    for signal in signals:
        conn.execute(
            """
            INSERT INTO strategic_signals
                (signal_type, title, analysis, confidence, competitor_id, supporting_event_ids, model_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal["signal_type"],
                signal["title"],
                signal["analysis"],
                _normalize_confidence(signal.get("confidence", 0.5)),
                signal.get("competitor_id"),
                json.dumps(signal.get("supporting_event_ids", [])),
                signal.get("model_version", "heuristic"),
            ),
        )
    conn.commit()
    conn.close()


def get_latest_signals(limit: int = 5):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT ss.*, c.slug AS competitor_slug, c.name AS competitor_name
        FROM strategic_signals ss
        LEFT JOIN competitors c ON c.id = ss.competitor_id
        ORDER BY ss.detected_at DESC, ss.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
