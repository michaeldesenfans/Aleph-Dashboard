"""Synthesis generation for macro trend, strategic signals, and widget themes."""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone

from openai import OpenAI

from server.config import OPENAI_API_KEY, OPENAI_MODEL, SIGNALS_MAX_AGE_MINUTES, SYNTHESIS_MAX_EVENTS, TREND_MAX_AGE_MINUTES
from server.repositories.events import get_events_for_synthesis
from server.repositories.synthesis import (
    get_latest_signals,
    get_latest_trend,
    get_momentum_snapshot,
    get_snapshot_count,
    replace_signals,
    save_momentum_snapshot,
    save_trend,
)

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
        "headline_trend": f"Competitive activity clustering around {headline.lower()} signals.",
        "why_it_matters": "Aleph should monitor this trend for potential impact on positioning and market share.",
        "key_driver": headline,
        "narrative": narrative,
        "key_datapoints": [],
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


def _event_detail(event: dict) -> str:
    meta = json.loads(event.get("metadata_json") or "{}")
    source = meta.get("source_name") or ""
    source_url = meta.get("source_url") or ""
    return (
        f"[{event.get('severity_label')}] {event.get('competitor_name') or event.get('competitor_slug') or 'Industry'} | "
        f"{event.get('event_type')}: {event.get('title')} "
        f"| Summary: {(event.get('summary') or '')[:200]} "
        f"| Source: {source} ({source_url})"
    )


def _call_openai_for_trend(events: list[dict]) -> dict | None:
    if not OPENAI_API_KEY or not events:
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = "\n".join(_event_detail(event) for event in events[:20])
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strategic intelligence analyst for Aleph Cloud, a decentralized cloud platform "
                        "competing against hyperscalers and GPU cloud providers. Analyze the competitive events below "
                        "and identify the SINGLE most important strategic trend.\n\n"
                        "Return JSON with these keys:\n"
                        "- title: concise headline (e.g. 'AI Infrastructure Arms Race Accelerates')\n"
                        "- headline_trend: one-sentence strategic thesis (the WHAT)\n"
                        "- why_it_matters: 2-3 sentences explaining strategic relevance to Aleph Cloud specifically (the SO WHAT)\n"
                        "- key_driver: the single most important causal factor driving this trend\n"
                        "- narrative: full 3-4 sentence analytical narrative\n"
                        "- key_datapoints: array of {label, value, source} — extract concrete figures "
                        "(dollar amounts, percentages, capacity metrics, dates) from the events\n"
                        "- confidence: float 0-1\n"
                        "- impact_level: 'critical' | 'high' | 'medium' | 'low'"
                    ),
                },
                {"role": "user", "content": f"Competitive events (last 30 days):\n{prompt}"},
            ],
            temperature=0.2,
            max_completion_tokens=800,
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
        # Ensure key_datapoints is a list
        if not isinstance(data.get("key_datapoints"), list):
            data["key_datapoints"] = []
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


def _call_openai_for_trend_article(events: list[dict], trend_summary: dict) -> dict | None:
    """Generate a full in-depth article for the macro trend, with structured sections and source-linked claims."""
    if not OPENAI_API_KEY or not events:
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        event_details = "\n".join(_event_detail(ev) for ev in events[:20])
        trend_context = (
            f"Title: {trend_summary.get('title')}\n"
            f"Thesis: {trend_summary.get('headline_trend')}\n"
            f"Why it matters: {trend_summary.get('why_it_matters')}\n"
            f"Key driver: {trend_summary.get('key_driver')}"
        )
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strategic intelligence analyst for Aleph Cloud, a decentralized cloud platform. "
                        "Write a structured in-depth article analyzing the macro competitive trend.\n\n"
                        "Return JSON with:\n"
                        "- full_article_md: A 5-8 paragraph markdown article with:\n"
                        "  - Opening paragraph with the strategic thesis\n"
                        "  - 3-4 sections with ## Section Headers\n"
                        "  - Inline source citations using (Source Name) format\n"
                        "  - Specific data points, competitor names, dollar figures, timelines\n"
                        "  - Concluding section: '## Strategic Implications for Aleph Cloud'\n"
                        "  - For each factual claim, tag the source name in parentheses\n\n"
                        "- article_sections: array of {heading, body_md, claims: [{text, source_name}]}\n"
                        "  Each claim is a factual statement with its source attribution\n"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"TREND SUMMARY:\n{trend_context}\n\n"
                        f"SUPPORTING EVENTS:\n{event_details}"
                    ),
                },
            ],
            temperature=0.3,
            max_completion_tokens=3000,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)
        return data
    except Exception as exc:
        logger.warning("OpenAI trend article generation failed: %s", exc)
        return None


def _resolve_claim_sources(claims: list[dict], events: list[dict]) -> list[dict]:
    """Match claim source_name values to actual URLs from event metadata.
    Uses fuzzy matching since GPT may output 'InfotechLead' while DB has 'infotechlead.com'.
    """
    import re

    # Build multiple lookup keys for each source
    source_entries: list[tuple[str, str, str]] = []  # (name, url, normalized)
    for ev in events:
        meta = json.loads(ev.get("metadata_json") or "{}")
        name = (meta.get("source_name") or "").strip()
        url = meta.get("source_url") or ""
        if name and url:
            # Create normalized form: lowercase, strip TLD, remove www/dots
            norm = re.sub(r'\.(com|org|net|io|ai|co|uk|de)$', '', name.lower().strip())
            norm = norm.replace('www.', '').replace('.', '').replace('-', '').replace('_', '')
            source_entries.append((name, url, norm))

    for claim in claims:
        src_name = (claim.get("source_name") or "").strip()
        if not src_name:
            claim.setdefault("source_url", "")
            continue
        # Normalize the GPT source name the same way
        claim_norm = re.sub(r'\.(com|org|net|io|ai|co|uk|de)$', '', src_name.lower())
        claim_norm = claim_norm.replace('www.', '').replace('.', '').replace('-', '').replace('_', '').replace(' ', '')
        # Try exact match first, then fuzzy
        matched_url = ""
        for name, url, norm in source_entries:
            if claim_norm == norm or claim_norm in norm or norm in claim_norm:
                matched_url = url
                break
        claim["source_url"] = matched_url
    return claims


# In-memory cache for trend article
_trend_article_cache: dict = {"data": None, "expires_at": 0.0}
TREND_ARTICLE_CACHE_SECONDS = 1800  # 30 minutes


def generate_trend_article(events: list[dict] | None = None, trend: dict | None = None) -> dict | None:
    """Generate or retrieve cached trend article."""
    import time

    now = time.time()
    cached = _trend_article_cache.get("data")
    if cached and _trend_article_cache.get("expires_at", 0) > now:
        return cached

    if events is None:
        events = get_events_for_synthesis(limit=SYNTHESIS_MAX_EVENTS)
    if trend is None:
        trend = get_latest_trend()
    if not trend:
        return None

    article_data = _call_openai_for_trend_article(events, trend)
    if not article_data:
        return None

    # Resolve claim sources to actual URLs
    sections = article_data.get("article_sections") or []
    for section in sections:
        section["claims"] = _resolve_claim_sources(section.get("claims") or [], events)

    result = {
        "full_article_md": article_data.get("full_article_md") or "",
        "article_sections": sections,
        "trend_title": trend.get("title"),
        "generated_at": trend.get("generated_at"),
    }
    _trend_article_cache["data"] = result
    _trend_article_cache["expires_at"] = now + TREND_ARTICLE_CACHE_SECONDS
    return result


TIER1_SOURCE_KEYWORDS = [
    "reuters", "bloomberg", "techcrunch", "register", "ars technica",
    "the verge", "cnbc", "financial times", "wall street", "zdnet",
    "venturebeat", "wired", "bsi", "enisa", "aws", "azure", "google cloud",
    "gcp", "oracle", "ibm", "infotechlead", "datacenter", "crn",
    "silicon angle", "cloud computing news", "cloud wars",
]


def compute_confidence_decomposition(events: list[dict], trend: dict) -> dict:
    """Break down WHY the synthesis has its confidence level."""
    source_names = set()
    tier1_count = 0
    competitors_covered = set()
    newest_ts = None
    oldest_ts = None

    for event in events:
        meta = json.loads(event.get("metadata_json") or "{}")
        source = (meta.get("source_name") or "").strip()
        if source:
            source_names.add(source)
            source_lower = source.lower()
            if any(kw in source_lower for kw in TIER1_SOURCE_KEYWORDS):
                tier1_count += 1

        comp = event.get("competitor_name") or event.get("competitor_slug")
        if comp:
            competitors_covered.add(comp)

        det = event.get("detected_at")
        if det:
            try:
                raw_dt = datetime.fromisoformat(det.replace("Z", "+00:00"))
                dt = raw_dt.astimezone(timezone.utc) if raw_dt.tzinfo else raw_dt.replace(tzinfo=timezone.utc)
                if newest_ts is None or dt > newest_ts:
                    newest_ts = dt
                if oldest_ts is None or dt < oldest_ts:
                    oldest_ts = dt
            except ValueError:
                pass

    now = datetime.now(timezone.utc)
    newest_days = round((now - newest_ts).total_seconds() / 86400, 1) if newest_ts else 0
    oldest_days = round((now - oldest_ts).total_seconds() / 86400, 1) if oldest_ts else 30

    total_events = max(len(events), 1)
    source_quality_pct = round(tier1_count / total_events * 100)

    # Signal agreement: what % of events share the same event_type as the dominant type
    type_counter = Counter(e.get("event_type") for e in events)
    dominant_count = type_counter.most_common(1)[0][1] if type_counter else 0
    signal_agreement_pct = round(dominant_count / total_events * 100)

    return {
        "overall_confidence": trend.get("confidence", 0.5),
        "independent_sources": len(source_names),
        "source_names": sorted(source_names)[:8],
        "source_quality_pct": min(source_quality_pct, 100),
        "evidence_recency": {
            "newest_days_ago": newest_days,
            "oldest_days_ago": oldest_days,
        },
        "coverage_breadth": {
            "covered": len(competitors_covered),
            "total_tracked": 17,
        },
        "signal_agreement_pct": min(signal_agreement_pct, 100),
    }


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


def _call_openai_for_theme_momentum(themes_with_events: list[dict]) -> dict | None:
    """Call OpenAI once for all themes, generating blurbs + detailed explorations.

    Returns a dict keyed by theme subject with {blurb, detailed_exploration} values,
    or None on failure.
    """
    if not OPENAI_API_KEY or not themes_with_events:
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        theme_blocks = []
        for theme in themes_with_events:
            events_text = "\n".join(
                f"  - [{ev.get('severity_label','?')}] {ev.get('competitor_name','?')} | "
                f"{ev.get('title','')} (source: {ev.get('source_name','unknown')})"
                for ev in theme["events"][:8]
            )
            theme_blocks.append(
                f"THEME: {theme['subject']} ({theme['attention']}, {theme['count']} signals)\n"
                f"Competitors: {', '.join(theme['competitors'][:5])}\n"
                f"Recent events:\n{events_text}"
            )
        prompt = "\n\n".join(theme_blocks)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strategic analyst for Aleph Cloud, a decentralized cloud platform. "
                        "For each competitive momentum theme below, generate:\n"
                        "1. A `blurb` (2-3 sentences) — a triangulated analytical summary that synthesizes "
                        "the underlying signals into a strategic insight. Do NOT just count signals; "
                        "extract the meaning and implications for Aleph Cloud.\n"
                        "2. A `detailed_exploration` (3-5 paragraphs of markdown) — an in-depth analysis "
                        "of the theme with specific claims. Cite sources inline using parenthetical "
                        "notation like (TechCrunch) or (source name). Bold key takeaways. "
                        "End with a brief strategic recommendation for Aleph Cloud.\n\n"
                        "Return JSON: {\"themes\": {\"Theme Name\": {\"blurb\": \"...\", \"detailed_exploration\": \"...\"}, ...}}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_completion_tokens=2500,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)
        return data.get("themes") or data
    except Exception as exc:
        logger.warning("OpenAI theme momentum synthesis failed: %s", exc)
        return None


# In-memory cache for theme momentum AI results
_theme_momentum_cache: dict = {"data": None, "expires_at": 0.0}
THEME_MOMENTUM_CACHE_SECONDS = 1800  # 30 minutes


def build_momentum_themes(rows: list[dict], theme_events: dict[str, list[dict]] | None = None) -> list[dict]:
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
                "count": count,
                "blurb": f"{theme_name} generated {count} tracked signals in the selected window across {len(competitors)} pinned competitors.",
                "detailed_exploration": None,
                "sources": [],
            }
        )

    # AI-enhanced blurbs + detailed explorations
    import time

    now = time.time()
    cached = _theme_momentum_cache.get("data")
    if cached and _theme_momentum_cache.get("expires_at", 0) > now:
        ai_themes = cached
    else:
        # Build event lists for each theme to feed the LLM
        themes_for_llm = []
        for theme in themes:
            event_type = {v: k for k, v in label_map.items() if k is not None}.get(theme["subject"])
            evts = (theme_events or {}).get(event_type or "", [])
            themes_for_llm.append({
                "subject": theme["subject"],
                "attention": theme["attention"],
                "count": theme["count"],
                "competitors": theme["competitors"],
                "events": evts,
            })
        ai_themes = _call_openai_for_theme_momentum(themes_for_llm)
        if ai_themes:
            _theme_momentum_cache["data"] = ai_themes
            _theme_momentum_cache["expires_at"] = now + THEME_MOMENTUM_CACHE_SECONDS

    if ai_themes:
        for theme in themes:
            ai_data = ai_themes.get(theme["subject"])
            if ai_data:
                theme["blurb"] = ai_data.get("blurb") or theme["blurb"]
                theme["detailed_exploration"] = ai_data.get("detailed_exploration")

    return themes


def capture_momentum_snapshot(themes: list[dict], window_days: int = 30):
    """Save today's theme momentum for historical comparison."""
    total = sum(t.get("count", 0) for t in themes)
    snap_themes = [
        {"subject": t["subject"], "count": t.get("count", 0), "attention": t.get("attention", "ACTIVE")}
        for t in themes
    ]
    save_momentum_snapshot(snap_themes, total, window_days)
    logger.info("Momentum snapshot saved: %d themes, %d total signals", len(snap_themes), total)


def compute_momentum_delta(current_themes: list[dict], lookback_days: int = 7, window_days: int = 30) -> list[dict]:
    """Compare today's themes to N days ago."""
    prev_snapshot = get_momentum_snapshot(days_ago=lookback_days, window_days=window_days)
    if not prev_snapshot:
        return []

    prev_themes = json.loads(prev_snapshot.get("themes_json") or "[]")
    prev_map: dict[str, dict] = {t["subject"]: t for t in prev_themes}

    deltas = []
    for theme in current_themes:
        subject = theme["subject"]
        current_count = theme.get("count", 0)
        prev_theme = prev_map.get(subject)
        prev_count = prev_theme["count"] if prev_theme else 0

        delta = current_count - prev_count
        delta_pct = round((delta / max(prev_count, 1)) * 100, 1)

        if prev_count == 0 and current_count > 0:
            direction = "emerging"
        elif current_count == 0 and prev_count > 2:
            direction = "dying"
        elif delta_pct > 50:
            direction = "surging"
        elif delta_pct > 10:
            direction = "rising"
        elif delta_pct < -30:
            direction = "falling"
        else:
            direction = "steady"

        deltas.append({
            "subject": subject,
            "current_count": current_count,
            "previous_count": prev_count,
            "delta": delta,
            "delta_pct": delta_pct,
            "trend_direction": direction,
            "is_new": prev_theme is None,
        })
    return deltas
