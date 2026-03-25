"""Repository for current and historical provider status."""

from __future__ import annotations

import json

from server.repositories.db import get_conn


DISPLAY_RANK = {"outage": 1, "degraded": 2, "unknown": 3, "clear": 4}


def update_provider_status(
    *,
    competitor_id: int,
    state: str,
    incidents: list[dict],
    source_endpoint_id: int | None = None,
    region_label: str | None = None,
    source_coverage: str = "full",
):
    conn = get_conn()
    active_incidents = [i for i in incidents if i.get("status") in ("active", "degraded", "monitoring")]
    latest = incidents[0] if incidents else {}
    payload = {
        "incidents": incidents[:5],
        "source_coverage": source_coverage,
    }
    conn.execute(
        """
        INSERT INTO provider_status_history
            (competitor_id, overall_state, region_label, active_incident_count, source_endpoint_id, payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            competitor_id,
            state,
            region_label,
            len(active_incidents),
            source_endpoint_id,
            json.dumps(payload),
        ),
    )
    conn.execute(
        """
        UPDATE provider_status_current
        SET overall_state = ?,
            region_label = ?,
            active_incident_count = ?,
            latest_incident_title = ?,
            latest_incident_url = ?,
            source_coverage = ?,
            freshness_seconds = 0,
            last_checked_at = datetime('now'),
            last_changed_at = datetime('now'),
            display_rank = ?,
            payload_json = ?
        WHERE competitor_id = ?
        """,
        (
            state,
            region_label,
            len(active_incidents),
            latest.get("title"),
            latest.get("incident_url"),
            source_coverage,
            DISPLAY_RANK.get(state, 4),
            json.dumps(payload),
            competitor_id,
        ),
    )
    conn.commit()
    conn.close()


def mark_provider_checked(competitor_id: int, *, source_coverage: str = "none"):
    conn = get_conn()
    conn.execute(
        """
        UPDATE provider_status_current
        SET freshness_seconds = 0,
            last_checked_at = datetime('now'),
            source_coverage = ?
        WHERE competitor_id = ?
        """,
        (source_coverage, competitor_id),
    )
    conn.commit()
    conn.close()


def set_provider_unknown(competitor_id: int, *, source_coverage: str = "none"):
    update_provider_status(
        competitor_id=competitor_id,
        state="unknown",
        incidents=[],
        source_coverage=source_coverage,
    )


def refresh_freshness():
    conn = get_conn()
    conn.execute(
        """
        UPDATE provider_status_current
        SET freshness_seconds = CAST((julianday('now') - julianday(COALESCE(last_checked_at, datetime('now')))) * 86400 AS INTEGER)
        """
    )
    conn.commit()
    conn.close()


def get_all_provider_status():
    refresh_freshness()
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT psc.*, c.slug, c.name, c.display_order
        FROM provider_status_current psc
        JOIN competitors c ON c.id = psc.competitor_id
        WHERE c.active = 1 AND c.is_pinned = 1
        ORDER BY psc.display_rank ASC, c.display_order ASC, psc.last_checked_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
