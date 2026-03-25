"""Widget-shaped read models for the V2 frontend."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from server.repositories.competitors import get_pinned_competitors
from server.repositories.discovery import get_budget_snapshot, get_recent_runs
from server.repositories.events import (
    get_headlines,
    get_incident_counts,
    get_momentum,
    get_recent_event_stats,
    get_watchlist_activity,
    query_events,
)
from server.repositories.status import get_all_provider_status
from server.services.synthesis import build_momentum_themes, ensure_synthesis


from server.repositories.db import get_conn as _get_conn

WINDOW_MAP = {"7d": 7, "30d": 30, "90d": 90}


def _enrich_theme_sources(themes: list[dict], window_days: int):
    """Add source links to momentum themes from recent events."""
    type_reverse_map = {
        "Infrastructure Launch Velocity": "launch",
        "Capital Formation": "funding",
        "Regulatory Positioning": "policy",
        "Go-to-Market Alliances": "partnership",
        "Price Pressure": "pricing",
        "Reliability Scrutiny": "outage",
        "General Competitive Activity": "news",
    }
    conn = _get_conn()
    for theme in themes:
        event_type = type_reverse_map.get(theme["subject"])
        if not event_type:
            continue
        rows = conn.execute(
            """
            SELECT metadata_json FROM events
            WHERE event_type = ? AND detected_at >= datetime('now', ?)
              AND metadata_json LIKE '%source_url%'
            ORDER BY severity_score DESC, detected_at DESC
            LIMIT 3
            """,
            (event_type, f"-{window_days} days"),
        ).fetchall()
        sources = []
        seen_urls = set()
        for row in rows:
            meta = json.loads(row["metadata_json"] or "{}")
            url = meta.get("source_url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append({"name": meta.get("source_name") or "", "url": url})
        theme["sources"] = sources
    conn.close()


def _resolve_event_sources(event_ids: set) -> dict:
    """Given event IDs, return {id: {name, url}} from event metadata."""
    if not event_ids:
        return {}
    conn = _get_conn()
    placeholders = ",".join("?" for _ in event_ids)
    rows = conn.execute(
        f"SELECT id, metadata_json FROM events WHERE id IN ({placeholders})",
        list(event_ids),
    ).fetchall()
    conn.close()
    result = {}
    for row in rows:
        meta = json.loads(row["metadata_json"] or "{}")
        url = meta.get("source_url")
        if url:
            result[row["id"]] = {
                "name": meta.get("source_name") or "",
                "url": url,
            }
    return result


def _parse_ts(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _relative_time(value: str | None) -> str:
    dt = _parse_ts(value)
    if not dt:
        return "unknown"
    diff = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    minutes = int(diff.total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def build_stats(pipeline_state: dict):
    stats = get_recent_event_stats(hours=24)
    return {
        "pipeline_live": not pipeline_state.get("running", False),
        "pipeline_running": pipeline_state.get("running", False),
        "events_24h": int(stats.get("total") or 0),
        "critical_24h": int(stats.get("critical_count") or 0),
        "high_24h": int(stats.get("high_count") or 0),
        "last_updated_at": stats.get("last_updated_at") or pipeline_state.get("last_run"),
    }


def build_csp_status():
    statuses = get_all_provider_status()
    items = []
    active_count = 0
    for row in statuses:
        state = row.get("overall_state") or "unknown"
        if state in ("outage", "degraded"):
            active_count += 1
        payload = json.loads(row.get("payload_json") or "{}")
        items.append(
            {
                "slug": row["slug"],
                "provider": row["name"],
                "state": state,
                "region_label": row.get("region_label"),
                "active_incident_count": int(row.get("active_incident_count") or 0),
                "latest_incident_title": row.get("latest_incident_title"),
                "latest_incident_url": row.get("latest_incident_url"),
                "freshness_seconds": int(row.get("freshness_seconds") or 0),
                "freshness_label": _relative_time(row.get("last_checked_at")),
                "source_coverage": row.get("source_coverage", "none"),
                "payload": payload,
            }
        )
    return {"items": items, "active_count": active_count}


def build_headlines():
    items = []
    for event in get_headlines(limit=3):
        meta = json.loads(event.get("metadata_json") or "{}")
        items.append(
            {
                "id": event["id"],
                "slug": event.get("competitor_slug"),
                "provider": event.get("competitor_name"),
                "severity": event.get("severity_label"),
                "event_type": event.get("event_type"),
                "headline": event.get("title"),
                "summary": event.get("summary"),
                "source_name": meta.get("source_name") or event.get("competitor_name"),
                "source_url": meta.get("source_url"),
                "detected_at": event.get("detected_at"),
                "relative_time": _relative_time(event.get("detected_at")),
                "tags": json.loads(event.get("tags_json") or "[]"),
            }
        )
    return {"items": items}


def build_events(
    *,
    competitor: str | None = None,
    event_type: str | None = None,
    severity: list[str] | None = None,
    limit: int = 30,
    hours: int | None = None,
):
    items = []
    for event in query_events(
        competitor_slug=competitor,
        event_type=event_type,
        severity=severity,
        limit=limit,
        since_hours=hours,
    ):
        meta = json.loads(event.get("metadata_json") or "{}")
        items.append(
            {
                "id": event["id"],
                "provider": event.get("competitor_name") or "Industry",
                "slug": event.get("competitor_slug"),
                "event_type": event.get("event_type"),
                "severity": event.get("severity_label"),
                "headline": event.get("title"),
                "summary": event.get("summary"),
                "strategic_impact": event.get("strategic_impact"),
                "source_url": meta.get("source_url"),
                "source_name": meta.get("source_name"),
                "detected_at": event.get("detected_at"),
                "relative_time": _relative_time(event.get("detected_at")),
                "tags": json.loads(event.get("tags_json") or "[]"),
            }
        )
    return {"items": items, "total": len(items)}


def build_momentum(window: str = "30d"):
    days = WINDOW_MAP.get(window, 30)
    rows = get_momentum(window_days=days)
    competitor_map = {}
    for competitor in get_pinned_competitors():
        competitor_map[competitor["slug"]] = {
            "name": competitor["name"],
            "slug": competitor["slug"],
            "counts": {"launch": 0, "funding": 0, "policy": 0, "partnership": 0, "pricing": 0, "outage": 0, "news": 0},
            "total_score": 0,
        }

    for row in rows:
        slug = row["slug"]
        event_type = row.get("event_type") or "news"
        count = int(row.get("count") or 0)
        if slug not in competitor_map:
            continue
        competitor_map[slug]["counts"][event_type] = count
        competitor_map[slug]["total_score"] += count

    themes = build_momentum_themes(rows)
    # Enrich themes with source URLs from recent events
    _enrich_theme_sources(themes, days)
    incident_counts = get_incident_counts(window_days=min(days, 30))
    watchlist = []
    for row in get_watchlist_activity(window_days=days, limit=6):
        slug = row["slug"]
        summary_parts = []
        if incident_counts.get(slug):
            summary_parts.append(f"{incident_counts[slug]} incidents / 7d")
        high_value = int(row.get("high_value_count") or 0)
        if high_value:
            summary_parts.append(f"{high_value} high-value signals")
        summary_parts.append(f"{int(row.get('event_count') or 0)} events / {days}d")
        watchlist.append(
            {
                "slug": slug,
                "name": row["name"],
                "summary": " · ".join(summary_parts),
                "event_count": int(row.get("event_count") or 0),
                "trend": "up" if high_value >= 3 else "flat",
            }
        )

    return {
        "window": window,
        "days": days,
        "competitors": list(competitor_map.values()),
        "themes": themes,
        "watchlist": watchlist,
    }


def build_trend():
    trend, _ = ensure_synthesis()
    if not trend:
        return {}
    return {
        "title": trend.get("title"),
        "narrative": trend.get("narrative"),
        "confidence": trend.get("confidence"),
        "impact_level": trend.get("impact_level"),
        "window_start": trend.get("window_start"),
        "window_end": trend.get("window_end"),
        "generated_at": trend.get("generated_at"),
    }


def _fallback_signal_sources(signal: dict, limit: int = 3) -> list[dict]:
    """Find source URLs from recent events matching signal keywords."""
    conn = _get_conn()
    # Use first meaningful word from signal title as search term
    title = signal.get("title") or ""
    slug = signal.get("competitor_slug")
    where = "metadata_json LIKE '%source_url%' AND detected_at >= datetime('now', '-30 days')"
    params: list = []
    if slug:
        where += " AND competitor_slug = ?"
        params.append(slug)
    rows = conn.execute(
        f"""SELECT metadata_json FROM events
        WHERE {where}
        ORDER BY severity_score DESC, detected_at DESC
        LIMIT ?""",
        params + [limit],
    ).fetchall()
    conn.close()
    sources = []
    seen = set()
    for row in rows:
        meta = json.loads(row["metadata_json"] or "{}")
        url = meta.get("source_url")
        if url and url not in seen:
            seen.add(url)
            sources.append({"name": meta.get("source_name") or "", "url": url})
    return sources


def build_signals():
    _, signals = ensure_synthesis()
    # Collect all supporting event IDs to resolve source URLs
    all_event_ids = set()
    for signal in signals:
        for eid in json.loads(signal.get("supporting_event_ids") or "[]"):
            all_event_ids.add(eid)
    event_sources = _resolve_event_sources(all_event_ids)

    items = []
    for signal in signals:
        event_ids = json.loads(signal.get("supporting_event_ids") or "[]")
        sources = [event_sources[eid] for eid in event_ids if eid in event_sources]
        # Fallback: if GPT returned fake event IDs, find sources from recent events
        if not sources:
            sources = _fallback_signal_sources(signal)
        items.append(
            {
                "id": signal["id"],
                "signal_type": signal["signal_type"],
                "title": signal["title"],
                "analysis": signal["analysis"],
                "confidence": signal["confidence"],
                "detected_at": signal["detected_at"],
                "relative_time": _relative_time(signal["detected_at"]),
                "competitor_slug": signal.get("competitor_slug"),
                "competitor_name": signal.get("competitor_name"),
                "sources": sources,
            }
        )
    return {"items": items}


def build_health(pipeline_state: dict):
    runs = get_recent_runs(limit=8)
    budget = get_budget_snapshot()
    return {
        "status": "ok",
        "pipeline_running": pipeline_state.get("running", False),
        "last_run": pipeline_state.get("last_run"),
        "last_summary": pipeline_state.get("last_summary"),
        "recent_runs": runs,
        "brave_budget": budget,
    }
