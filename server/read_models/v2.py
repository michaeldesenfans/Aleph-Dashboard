"""Widget-shaped read models for the V2 frontend."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from server.repositories.competitors import get_pinned_competitors
from server.repositories.discovery import get_budget_snapshot, get_recent_runs
from server.repositories.events import (
    get_competitor_activity_matrix,
    get_distribution_by_type,
    get_headlines,
    get_incident_counts,
    get_key_evidence_events,
    get_momentum,
    get_recent_event_stats,
    get_signal_volume_by_day,
    get_watchlist_activity,
    get_window_stats,
    query_events,
)
from server.repositories.status import get_all_provider_status
from server.services.synthesis import (
    build_momentum_themes,
    capture_momentum_snapshot,
    compute_confidence_decomposition,
    compute_momentum_delta,
    ensure_synthesis,
    generate_trend_article,
)
from server.repositories.synthesis import get_snapshot_count, get_theme_trajectory
from server.repositories.events import get_events_for_synthesis


from server.repositories.db import get_conn as _get_conn

WINDOW_MAP = {"7d": 7, "30d": 30, "90d": 90}


def _fetch_theme_events(window_days: int) -> dict[str, list[dict]]:
    """Fetch recent events grouped by event_type for AI momentum synthesis."""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT e.event_type, e.title, e.summary, e.severity_label,
               c.name AS competitor_name, e.metadata_json
        FROM events e
        LEFT JOIN competitors c ON c.id = e.competitor_id
        WHERE e.detected_at >= datetime('now', ?)
          AND e.lifecycle_status IN ('active', 'resolved')
        ORDER BY e.severity_score DESC, e.detected_at DESC
        """,
        (f"-{window_days} days",),
    ).fetchall()
    conn.close()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        et = row["event_type"] or "news"
        if et not in grouped:
            grouped[et] = []
        if len(grouped[et]) < 8:
            meta = json.loads(row["metadata_json"] or "{}")
            grouped[et].append({
                "title": row["title"],
                "summary": row["summary"],
                "severity_label": row["severity_label"],
                "competitor_name": row["competitor_name"],
                "source_name": meta.get("source_name") or "",
                "source_url": meta.get("source_url") or "",
            })
    return grouped


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

    # Fetch recent events per event_type for AI-enhanced momentum blurbs
    theme_events = _fetch_theme_events(days)
    themes = build_momentum_themes(rows, theme_events=theme_events)
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

    # Capture daily momentum snapshot (deduped by date)
    capture_momentum_snapshot(themes, window_days=days)

    # Compute theme deltas vs 7 days ago
    theme_deltas = compute_momentum_delta(themes, lookback_days=7, window_days=days)

    # Window proof data
    window_stats = get_window_stats(days)
    total_signals = int(window_stats.get("total_signals") or 0)
    oldest = window_stats.get("oldest_event")
    newest = window_stats.get("newest_event")
    days_with_data = len(get_signal_volume_by_day(days))

    return {
        "window": window,
        "days": days,
        "window_proof": {
            "window_start": oldest,
            "window_end": newest,
            "total_signals_in_window": total_signals,
            "signals_per_day_avg": round(total_signals / max(days_with_data, 1), 1),
            "snapshot_count": get_snapshot_count(days),
        },
        "theme_deltas": theme_deltas,
        "competitors": list(competitor_map.values()),
        "themes": themes,
        "watchlist": watchlist,
    }


def build_trend():
    trend, _ = ensure_synthesis()
    if not trend:
        return {}
    key_datapoints = trend.get("key_datapoints_json") or trend.get("key_datapoints") or "[]"
    if isinstance(key_datapoints, str):
        key_datapoints = json.loads(key_datapoints)
    return {
        "title": trend.get("title"),
        "headline_trend": trend.get("headline_trend"),
        "why_it_matters": trend.get("why_it_matters"),
        "key_driver": trend.get("key_driver"),
        "key_datapoints": key_datapoints,
        "narrative": trend.get("narrative"),
        "confidence": trend.get("confidence"),
        "impact_level": trend.get("impact_level"),
        "window_start": trend.get("window_start"),
        "window_end": trend.get("window_end"),
        "generated_at": trend.get("generated_at"),
    }


def build_trend_article():
    """Build the full trend article with sections, claim sources, and evidence components."""
    events = get_events_for_synthesis(limit=60)
    trend = build_trend()

    article = generate_trend_article(events=events, trend=trend)
    if not article:
        article = {"full_article_md": "", "article_sections": [], "generated_at": None}

    # Component A: Key Evidence Timeline
    key_evidence = get_key_evidence_events(window_days=30, limit=8)
    article["key_evidence"] = [
        {
            "id": ev["id"],
            "title": ev["title"],
            "competitor": ev.get("competitor_name") or "",
            "slug": ev.get("competitor_slug") or "",
            "event_type": ev.get("event_type") or "news",
            "severity": ev.get("severity_label") or "Medium",
            "detected_at": ev.get("detected_at") or "",
            "source_name": ev.get("source_name") or "",
            "source_url": ev.get("source_url") or "",
            "short_label": ev.get("short_label") or "",
        }
        for ev in key_evidence
    ]

    # Component B: Confidence Decomposition
    article["confidence_decomposition"] = compute_confidence_decomposition(events, trend)

    # Component C: Theme Trajectory
    article["theme_trajectory"] = get_theme_trajectory(window_days=30, lookback_snapshots=4)

    return article


def build_trend_chart_data(window_days: int = 30) -> dict:
    """Pre-compute chart-ready data for the trend article."""
    volume = get_signal_volume_by_day(window_days)
    distribution = get_distribution_by_type(window_days)
    heatmap = get_competitor_activity_matrix(window_days)
    window = get_window_stats(window_days)

    total = int(window.get("total_signals") or 0)
    critical = int(window.get("critical_count") or 0)
    active_comp = int(window.get("active_competitors") or 0)
    days_with_data = len(volume)
    avg_per_day = round(total / max(days_with_data, 1), 1)

    return {
        "signal_volume_by_day": volume,
        "distribution_by_type": distribution,
        "competitor_activity_heatmap": heatmap,
        "top_statistics": [
            {"label": f"Total Signals ({window_days}d)", "value": str(total), "delta": "", "direction": "flat"},
            {"label": "Critical Events", "value": str(critical), "delta": "", "direction": "up" if critical > 0 else "flat"},
            {"label": "Active Competitors", "value": str(active_comp), "delta": "", "direction": "flat"},
            {"label": "Avg/Day", "value": str(avg_per_day), "delta": "", "direction": "flat"},
        ],
        "window": {
            "start": window.get("oldest_event"),
            "end": window.get("newest_event"),
            "total_signals": total,
            "days_with_data": days_with_data,
        },
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
