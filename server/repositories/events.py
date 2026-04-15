"""Repository for canonical events, incidents, and evidence links."""

from __future__ import annotations

import json

from server.repositories.db import get_conn


def insert_event(event: dict) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO events
                (event_key, event_type, competitor_id, title, summary, strategic_impact,
                 severity_score, severity_label, confidence, lifecycle_status, started_at,
                 detected_at, resolved_at, primary_region, metadata_json, tags_json,
                 extraction_version, synthesis_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("event_key"),
                event["event_type"],
                event.get("competitor_id"),
                event["title"],
                event.get("summary", ""),
                event.get("strategic_impact", ""),
                event.get("severity_score", 3),
                event.get("severity_label", "Medium"),
                event.get("confidence", 0.5),
                event.get("lifecycle_status", "active"),
                event.get("started_at"),
                event.get("detected_at"),
                event.get("resolved_at"),
                event.get("primary_region"),
                json.dumps(event.get("metadata", {})),
                json.dumps(event.get("tags", [])),
                event.get("extraction_version", "v2.0"),
                event.get("synthesis_version", "v2.0"),
            ),
        )
        conn.commit()
        event_id = cur.lastrowid
    except Exception:
        row = conn.execute("SELECT id FROM events WHERE event_key = ?", (event.get("event_key"),)).fetchone()
        event_id = row["id"] if row else -1
    conn.close()
    return event_id


def link_evidence(event_id: int, document_id: int, role: str = "source", confidence: float = 0.5):
    conn = get_conn()
    conn.execute(
        """
        INSERT OR IGNORE INTO event_evidence
            (event_id, document_id, evidence_role, extraction_confidence)
        VALUES (?, ?, ?, ?)
        """,
        (event_id, document_id, role, confidence),
    )
    conn.commit()
    conn.close()


def insert_incident(incident: dict) -> int:
    conn = get_conn()
    external_id = incident.get("external_incident_id") or incident.get("incident_url") or incident["title"]
    try:
        cur = conn.execute(
            """
            INSERT INTO incidents
                (competitor_id, event_id, external_incident_id, title, summary, status, severity,
                 region_label, affected_services, incident_url, first_seen_at, last_seen_at,
                 resolved_at, source_endpoint_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), datetime('now'), ?, ?, ?)
            """,
            (
                incident["competitor_id"],
                incident.get("event_id"),
                external_id,
                incident["title"],
                incident.get("summary", ""),
                incident.get("status", "active"),
                incident.get("severity", "minor"),
                incident.get("region_label"),
                json.dumps(incident.get("affected_services", [])),
                incident.get("incident_url"),
                incident.get("started_at"),
                incident.get("resolved_at"),
                incident.get("source_endpoint_id"),
                json.dumps(incident.get("metadata", {})),
            ),
        )
        conn.commit()
        incident_id = cur.lastrowid
    except Exception:
        conn.execute(
            """
            UPDATE incidents
            SET title = ?, summary = ?, status = ?, severity = ?, region_label = ?,
                affected_services = ?, incident_url = ?, last_seen_at = datetime('now'),
                resolved_at = ?, metadata_json = ?
            WHERE competitor_id = ? AND external_incident_id = ?
            """,
            (
                incident["title"],
                incident.get("summary", ""),
                incident.get("status", "active"),
                incident.get("severity", "minor"),
                incident.get("region_label"),
                json.dumps(incident.get("affected_services", [])),
                incident.get("incident_url"),
                incident.get("resolved_at"),
                json.dumps(incident.get("metadata", {})),
                incident["competitor_id"],
                external_id,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM incidents WHERE competitor_id = ? AND external_incident_id = ?",
            (incident["competitor_id"], external_id),
        ).fetchone()
        incident_id = row["id"]
    conn.close()
    return incident_id


def query_events(
    *,
    competitor_slug: str | None = None,
    event_type: str | None = None,
    severity: list[str] | None = None,
    limit: int = 50,
    since_hours: int | None = None,
    lifecycle: str = "active",
):
    conn = get_conn()
    clauses = []
    params: list = []
    if lifecycle:
        clauses.append("e.lifecycle_status = ?")
        params.append(lifecycle)
    if competitor_slug:
        clauses.append("c.slug = ?")
        params.append(competitor_slug)
    if event_type:
        clauses.append("e.event_type = ?")
        params.append(event_type)
    if severity:
        placeholders = ",".join("?" for _ in severity)
        clauses.append(f"e.severity_label IN ({placeholders})")
        params.extend(severity)
    if since_hours:
        clauses.append("e.detected_at >= datetime('now', ?)")
        params.append(f"-{since_hours} hours")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT e.*, c.slug AS competitor_slug, c.name AS competitor_name
        FROM events e
        LEFT JOIN competitors c ON c.id = e.competitor_id
        {where}
        ORDER BY e.severity_score DESC, e.detected_at DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_headlines(limit: int = 3):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT e.*, c.slug AS competitor_slug, c.name AS competitor_name
        FROM events e
        LEFT JOIN competitors c ON c.id = e.competitor_id
        WHERE e.lifecycle_status = 'active'
          AND e.severity_label IN ('Critical', 'High')
        ORDER BY e.severity_score DESC, e.detected_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_event_stats(hours: int = 24):
    conn = get_conn()
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN severity_label = 'Critical' THEN 1 ELSE 0 END) AS critical_count,
               SUM(CASE WHEN severity_label = 'High' THEN 1 ELSE 0 END) AS high_count,
               MAX(updated_at) AS last_updated_at
        FROM events
        WHERE detected_at >= datetime('now', ?)
        """,
        (f"-{hours} hours",),
    ).fetchone()
    conn.close()
    return dict(row)


def get_events_for_synthesis(limit: int = 60, hours: int = 720):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT e.*, c.slug AS competitor_slug, c.name AS competitor_name
        FROM events e
        LEFT JOIN competitors c ON c.id = e.competitor_id
        WHERE e.detected_at >= datetime('now', ?)
          AND e.severity_label IN ('Critical', 'High', 'Medium')
        ORDER BY e.severity_score DESC, e.detected_at DESC
        LIMIT ?
        """,
        (f"-{hours} hours", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_momentum(window_days: int = 30):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT c.slug, c.name, c.display_order, e.event_type, COUNT(*) AS count
        FROM competitors c
        LEFT JOIN events e
            ON e.competitor_id = c.id
           AND e.detected_at >= datetime('now', ?)
           AND e.lifecycle_status IN ('active', 'resolved')
        WHERE c.active = 1 AND c.is_pinned = 1
        GROUP BY c.slug, c.name, c.display_order, e.event_type
        ORDER BY c.display_order, e.event_type
        """,
        (f"-{window_days} days",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_watchlist_activity(window_days: int = 30, limit: int = 6):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT c.slug,
               c.name,
               c.display_order,
               COUNT(e.id) AS event_count,
               SUM(CASE WHEN e.severity_label IN ('Critical', 'High') THEN 1 ELSE 0 END) AS high_value_count,
               MAX(e.detected_at) AS last_event_at
        FROM competitors c
        LEFT JOIN events e
            ON e.competitor_id = c.id
           AND e.detected_at >= datetime('now', ?)
        WHERE c.active = 1 AND c.is_pinned = 1
        GROUP BY c.id, c.slug, c.name, c.display_order
        ORDER BY event_count DESC, high_value_count DESC, c.display_order
        LIMIT ?
        """,
        (f"-{window_days} days", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_incident_counts(window_days: int = 7):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT c.slug, COUNT(i.id) AS incident_count
        FROM competitors c
        LEFT JOIN incidents i
            ON i.competitor_id = c.id
           AND i.first_seen_at >= datetime('now', ?)
        GROUP BY c.slug
        """,
        (f"-{window_days} days",),
    ).fetchall()
    conn.close()
    return {row["slug"]: row["incident_count"] for row in rows}


def get_latest_events(limit: int = 10):
    return query_events(limit=limit, lifecycle=None)


def get_key_evidence_events(window_days: int = 30, limit: int = 8) -> list[dict]:
    """Return the top N most significant events in the window, with source URLs.
    Ordered by severity_score DESC, then detected_at DESC."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT e.id, e.title, e.event_type, e.severity_label, e.severity_score,
               e.detected_at, e.metadata_json,
               c.name AS competitor_name, c.slug AS competitor_slug
        FROM events e
        LEFT JOIN competitors c ON c.id = e.competitor_id
        WHERE e.detected_at >= datetime('now', ?)
          AND e.lifecycle_status IN ('active', 'resolved')
          AND e.severity_label IN ('Critical', 'High')
        ORDER BY e.severity_score DESC, e.detected_at DESC
        LIMIT ?
        """,
        (f"-{window_days} days", limit),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        r = dict(row)
        meta = json.loads(r.get("metadata_json") or "{}")
        r["source_name"] = meta.get("source_name") or ""
        r["source_url"] = meta.get("source_url") or ""
        # Create short label from title (first ~40 chars)
        title = r.get("title") or ""
        r["short_label"] = title[:40] + ("..." if len(title) > 40 else "")
        result.append(r)
    return result


def get_signal_volume_by_day(window_days: int = 30) -> list[dict]:
    """Daily signal count over the window."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT date(detected_at) AS date,
               COUNT(*) AS count,
               SUM(CASE WHEN severity_label = 'Critical' THEN 1 ELSE 0 END) AS critical
        FROM events
        WHERE detected_at >= datetime('now', ?)
          AND lifecycle_status IN ('active', 'resolved')
        GROUP BY date(detected_at)
        ORDER BY date(detected_at)
        """,
        (f"-{window_days} days",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_distribution_by_type(window_days: int = 30) -> list[dict]:
    """Signal count grouped by event_type."""
    label_map = {
        "launch": "Infrastructure Launch",
        "funding": "Capital Formation",
        "policy": "Regulatory",
        "partnership": "Alliances",
        "pricing": "Pricing",
        "outage": "Outages",
        "news": "General Activity",
    }
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT event_type AS type, COUNT(*) AS count
        FROM events
        WHERE detected_at >= datetime('now', ?)
          AND lifecycle_status IN ('active', 'resolved')
        GROUP BY event_type
        ORDER BY count DESC
        """,
        (f"-{window_days} days",),
    ).fetchall()
    conn.close()
    return [{"type": r["type"], "count": r["count"], "label": label_map.get(r["type"], r["type"])} for r in rows]


def get_competitor_activity_matrix(window_days: int = 30) -> list[dict]:
    """Competitor × event_type matrix."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT c.name AS competitor, c.slug,
               SUM(CASE WHEN e.event_type = 'launch' THEN 1 ELSE 0 END) AS launch,
               SUM(CASE WHEN e.event_type = 'funding' THEN 1 ELSE 0 END) AS funding,
               SUM(CASE WHEN e.event_type = 'policy' THEN 1 ELSE 0 END) AS policy,
               SUM(CASE WHEN e.event_type = 'partnership' THEN 1 ELSE 0 END) AS partnership,
               SUM(CASE WHEN e.event_type = 'pricing' THEN 1 ELSE 0 END) AS pricing,
               SUM(CASE WHEN e.event_type = 'outage' THEN 1 ELSE 0 END) AS outage,
               SUM(CASE WHEN e.event_type = 'news' THEN 1 ELSE 0 END) AS news,
               COUNT(e.id) AS total
        FROM competitors c
        JOIN events e ON e.competitor_id = c.id
        WHERE e.detected_at >= datetime('now', ?)
          AND e.lifecycle_status IN ('active', 'resolved')
          AND c.is_pinned = 1
        GROUP BY c.id, c.name, c.slug
        HAVING total > 0
        ORDER BY total DESC
        LIMIT 10
        """,
        (f"-{window_days} days",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_window_stats(window_days: int = 30) -> dict:
    """Aggregate stats for the synthesis window."""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT COUNT(*) AS total_signals,
               MIN(detected_at) AS oldest_event,
               MAX(detected_at) AS newest_event,
               SUM(CASE WHEN severity_label = 'Critical' THEN 1 ELSE 0 END) AS critical_count,
               COUNT(DISTINCT competitor_id) AS active_competitors
        FROM events
        WHERE detected_at >= datetime('now', ?)
          AND lifecycle_status IN ('active', 'resolved')
        """,
        (f"-{window_days} days",),
    ).fetchone()
    conn.close()
    return dict(row)
