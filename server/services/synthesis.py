"""Synthesis generation for macro trend, strategic signals, and widget themes."""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone

from openai import OpenAI

from server.config import OPENAI_API_KEY, OPENAI_MODEL, SIGNALS_MAX_AGE_MINUTES, SYNTHESIS_MAX_EVENTS, TREND_MAX_AGE_MINUTES
from server.repositories.events import get_events_for_synthesis
from server.repositories.synthesis import get_latest_signals, get_latest_trend, replace_signals, save_trend

logger = logging.getLogger(__name__)


def _parse_timestamp(value: str | None):
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _is_fresh(value: str | None, max_age_minutes: int) -> bool:
    dt = _parse_timestamp(value)
    if not dt:
        return False
    return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() <= max_age_minutes * 60


def _event_brief(event: dict) -> str:
    return f"[{event.get('severity_label')}] {event.get('competitor_name') or event.get('competitor_slug') or 'Industry'} | {event.get('event_type')}: {event.get('title')}"


def _heuristic_trend(events: list[dict]) -> dict:
    tag_counter = Counter()
    for event in events:
        for tag in json.loads(event.get("tags_json") or "[]"):
            tag_counter[tag] += 1

    headline = tag_counter.most_common(1)[0][0] if tag_counter else "Competitive execution"
    narrative = "Recent competitive activity is clustering around high-consequence cloud execution moves."
    if events:
        top_events = "; ".join(_event_brief(event) for event in events[:3])
        narrative = f"{top_events}. Aleph should treat this as an active execution window rather than passive market noise."

    return {
        "title": f"Macro Trend: {headline}" if not headline.lower().startswith("macro trend") else headline,
        "narrative": narrative,
        "confidence": 0.72,
        "impact_level": "high" if any(e.get("severity_label") == "Critical" for e in events) else "medium",
        "window_start": events[-1].get("detected_at") if events else None,
        "window_end": events[0].get("detected_at") if events else None,
        "evidence_event_ids": [event["id"] for event in events[:8]],
        "model_version": "heuristic",
    }


def _heuristic_signals(events: list[dict]) -> list[dict]:
    type_map = {
        "outage": "threat",
        "policy": "regulatory",
        "funding": "market_shift",
        "launch": "opportunity",
        "pricing": "threat",
        "partnership": "market_shift",
        "news": "opportunity",
    }
    signals = []
    for event in events[:5]:
        signal_type = type_map.get(event.get("event_type"), "market_shift")
        signals.append(
            {
                "signal_type": signal_type,
                "title": event.get("title", "")[:80],
                "analysis": event.get("strategic_impact") or event.get("summary") or event.get("title"),
                "confidence": min(max(float(event.get("confidence") or 0.5), 0.3), 0.98),
                "competitor_id": event.get("competitor_id"),
                "supporting_event_ids": [event["id"]],
                "model_version": "heuristic",
            }
        )
    return signals


def _call_openai_for_trend(events: list[dict]) -> dict | None:
    if not OPENAI_API_KEY or not events:
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = "\n".join(_event_brief(event) for event in events[:12])
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You synthesize cloud competitive intelligence for Aleph Cloud. "
                        "Return JSON with keys title, narrative, confidence, impact_level."
                    ),
                },
                {"role": "user", "content": f"Events:\n{prompt}"},
            ],
            temperature=0.2,
            max_completion_tokens=350,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)
        # Normalize confidence to float (GPT may return "High"/"Medium" etc.)
        conf_map = {"critical": 0.95, "high": 0.85, "medium": 0.65, "low": 0.45}
        raw_conf = data.get("confidence", 0.7)
        if isinstance(raw_conf, str):
            data["confidence"] = conf_map.get(raw_conf.lower(), 0.7)
        else:
            data["confidence"] = float(raw_conf)
        data["window_start"] = events[-1].get("detected_at")
        data["window_end"] = events[0].get("detected_at")
        data["evidence_event_ids"] = [event["id"] for event in events[:8]]
        data["model_version"] = OPENAI_MODEL
        return data
    except Exception as exc:
        logger.warning("OpenAI trend synthesis failed, using heuristic fallback: %s", exc)
        return None


def _call_openai_for_signals(events: list[dict]) -> list[dict] | None:
    if not OPENAI_API_KEY or not events:
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = "\n".join(_event_brief(event) for event in events[:12])
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate up to 5 strategic signal cards for Aleph Cloud. "
                        "Each signal should reference which competitor(s) it relates to. "
                        "Return JSON: {\"signals\": [{\"signal_type\": ..., \"title\": ..., "
                        "\"analysis\": ..., \"confidence\": 0.0, \"competitor\": \"competitor name\"}]}"
                    ),
                },
                {"role": "user", "content": f"Events:\n{prompt}"},
            ],
            temperature=0.2,
            max_completion_tokens=700,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        payload = json.loads(raw)
        signals = payload.get("signals") or []
        # Build competitor name → event ID lookup from the input events
        comp_event_map: dict[str, list[int]] = {}
        for ev in events:
            name = (ev.get("competitor_name") or ev.get("competitor_slug") or "").lower()
            if name:
                comp_event_map.setdefault(name, []).append(ev["id"])
        for signal in signals:
            signal.setdefault("model_version", OPENAI_MODEL)
            # Resolve supporting_event_ids from competitor name instead of GPT indices
            comp_name = (signal.pop("competitor", "") or "").lower()
            matched_ids = comp_event_map.get(comp_name, [])
            signal["supporting_event_ids"] = matched_ids[:3]
        return signals[:5]
    except Exception as exc:
        logger.warning("OpenAI signal synthesis failed, using heuristic fallback: %s", exc)
        return None


def ensure_synthesis():
    events = get_events_for_synthesis(limit=SYNTHESIS_MAX_EVENTS)

    trend = get_latest_trend()
    if not trend or not _is_fresh(trend.get("generated_at"), TREND_MAX_AGE_MINUTES):
        generated_trend = _call_openai_for_trend(events) or _heuristic_trend(events)
        save_trend(generated_trend)
        trend = get_latest_trend()

    signals = get_latest_signals(limit=5)
    if not signals or not _is_fresh(signals[0].get("detected_at"), SIGNALS_MAX_AGE_MINUTES):
        generated_signals = _call_openai_for_signals(events) or _heuristic_signals(events)
        replace_signals(generated_signals)
        signals = get_latest_signals(limit=5)

    return trend, signals


def build_momentum_themes(rows: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = defaultdict(lambda: {"count": 0, "competitors": set()})
    label_map = {
        "launch": "Infrastructure Launch Velocity",
        "funding": "Capital Formation",
        "policy": "Regulatory Positioning",
        "partnership": "Go-to-Market Alliances",
        "pricing": "Price Pressure",
        "outage": "Reliability Scrutiny",
        "news": "General Competitive Activity",
        None: "General Competitive Activity",
    }
    for row in rows:
        event_type = row.get("event_type")
        theme = label_map.get(event_type, "General Competitive Activity")
        grouped[theme]["count"] += int(row.get("count") or 0)
        if row.get("name"):
            grouped[theme]["competitors"].add(row["name"])

    ranked = sorted(grouped.items(), key=lambda item: item[1]["count"], reverse=True)[:6]
    themes = []
    for idx, (theme_name, payload) in enumerate(ranked):
        count = payload["count"]
        attention = "SURGING" if idx == 0 and count > 0 else "RISING" if count >= 4 else "ACTIVE"
        competitors = sorted(payload["competitors"])[:5]
        themes.append(
            {
                "subject": theme_name,
                "attention": attention,
                "competitors": competitors,
                "blurb": f"{theme_name} generated {count} tracked signals in the selected window across {len(competitors)} pinned competitors.",
                "sources": [],
            }
        )
    return themes
