"""Repository for synthesis outputs."""

from __future__ import annotations

import json

from server.repositories.db import get_conn


def save_trend(trend: dict) -> int:
    conn = get_conn()
    cur = conn.execute(
        """
        INSERT INTO trend_snapshots
            (title, narrative, confidence, impact_level, window_start, window_end,
             evidence_event_ids, model_version,
             headline_trend, why_it_matters, key_driver, key_datapoints_json,
             full_article_md, article_sections_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            trend.get("headline_trend"),
            trend.get("why_it_matters"),
            trend.get("key_driver"),
            json.dumps(trend.get("key_datapoints", [])),
            trend.get("full_article_md"),
            json.dumps(trend.get("article_sections", [])),
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


def save_momentum_snapshot(themes: list[dict], total_signals: int, window_days: int = 30) -> int | None:
    """Save today's momentum snapshot, deduped by date + window."""
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO momentum_snapshots (snapshot_date, window_days, themes_json, total_signals, generated_at)
            VALUES (date('now'), ?, ?, ?, datetime('now'))
            """,
            (window_days, json.dumps(themes), total_signals),
        )
        conn.commit()
        snap_id = cur.lastrowid
    except Exception:
        # Already have a snapshot for today — update it
        conn.execute(
            """
            UPDATE momentum_snapshots
            SET themes_json = ?, total_signals = ?, generated_at = datetime('now')
            WHERE snapshot_date = date('now') AND window_days = ?
            """,
            (json.dumps(themes), total_signals, window_days),
        )
        conn.commit()
        snap_id = None
    conn.close()
    return snap_id


def get_momentum_snapshot(days_ago: int = 7, window_days: int = 30) -> dict | None:
    """Get the momentum snapshot from N days ago, falling back to oldest available."""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT * FROM momentum_snapshots
        WHERE snapshot_date <= date('now', ?)
          AND window_days = ?
        ORDER BY snapshot_date DESC
        LIMIT 1
        """,
        (f"-{days_ago} days", window_days),
    ).fetchone()
    if not row:
        # Fallback: get the oldest snapshot that isn't today's
        row = conn.execute(
            """
            SELECT * FROM momentum_snapshots
            WHERE snapshot_date < date('now')
              AND window_days = ?
            ORDER BY snapshot_date ASC
            LIMIT 1
            """,
            (window_days,),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_snapshot_count(window_days: int = 30) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM momentum_snapshots WHERE window_days = ?",
        (window_days,),
    ).fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0


def get_theme_trajectory(window_days: int = 30, lookback_snapshots: int = 4) -> list[dict]:
    """For each theme, collect signal counts from the last N snapshots.
    Returns per-theme trajectory data for sparklines and trend direction."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT snapshot_date, themes_json, total_signals
        FROM momentum_snapshots
        WHERE window_days = ?
        ORDER BY snapshot_date DESC
        LIMIT ?
        """,
        (window_days, lookback_snapshots),
    ).fetchall()
    conn.close()
    if not rows:
        return []

    snapshots = [dict(r) for r in reversed(rows)]  # oldest first
    # Build per-theme history
    theme_map: dict[str, dict] = {}
    for snap in snapshots:
        import json as _json
        themes = _json.loads(snap.get("themes_json") or "[]")
        for t in themes:
            subject = t["subject"]
            if subject not in theme_map:
                theme_map[subject] = {
                    "subject": subject,
                    "history": [],
                    "first_seen_date": snap["snapshot_date"],
                }
            theme_map[subject]["history"].append({
                "date": snap["snapshot_date"],
                "count": t.get("count", 0),
            })

    # Compute delta and direction for each theme
    result = []
    for subject, data in theme_map.items():
        history = data["history"]
        current = history[-1]["count"] if history else 0
        oldest = history[0]["count"] if history else 0
        delta = current - oldest
        delta_pct = round((delta / max(oldest, 1)) * 100, 1)

        if len(history) == 1 and current > 0:
            direction = "new"
        elif delta_pct > 50:
            direction = "surging"
        elif delta_pct > 10:
            direction = "rising"
        elif delta_pct < -40:
            direction = "fading"
        elif delta_pct < -10:
            direction = "cooling"
        else:
            direction = "steady"

        result.append({
            "subject": subject,
            "current_count": current,
            "history": history,
            "delta_pct": delta_pct,
            "trend_direction": direction,
            "first_seen_date": data["first_seen_date"],
        })
    # Sort by current count desc
    result.sort(key=lambda x: x["current_count"], reverse=True)
    return result


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
