"""
Tool: analyze_impact.py
Layer: 3 — Execution
SOP: architecture/competitive_monitoring_sop.md

Uses OpenAI (gpt-4o) to:
  1. Identify the competitor in each raw signal
  2. Classify the event category
  3. Score strategic impact for Aleph Cloud (1-10)
  4. Generate a 1-sentence summary and 2-sentence strategic_impact

Input:  .tmp/deduped_signals.json
Output: .tmp/analyzed_signals.json — list of CompetitorEvent (pre-storage)
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger(__name__)

TMP_DIR = ROOT / ".tmp"
INPUT_FILE = TMP_DIR / "deduped_signals.json"
OUTPUT_FILE = TMP_DIR / "analyzed_signals.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

VALID_COMPETITORS = [
    "AWS", "Azure", "GCP", "OVHcloud", "Scaleway",
    "Hetzner", "DigitalOcean", "CoreWeave", "IONOS", "Other"
]
VALID_CATEGORIES = ["Outage", "Funding", "Product Launch", "News", "Policy"]

# Aleph Cloud strategic context injected into every prompt
ALEPH_CONTEXT = """
Aleph Cloud is a European cloud infrastructure startup targeting developer-led teams outgrowing
simple clouds (Hetzner, DigitalOcean) who need an EU-native, production-ready platform with
Managed K8s, S3-compatible storage, H100/H200 GPUs, and a path to sovereign compliance
(SecNumCloud, BSI C5). Aleph occupies the transition layer between developer clouds and
sovereign enterprise clouds. Key differentiators: transparent pricing, strong DX, EU legal entity,
confidential computing (AMD SEV-SNP), and EU data residency.
"""

SYSTEM_PROMPT = f"""You are a competitive intelligence analyst for Aleph Cloud.

Aleph Cloud context:
{ALEPH_CONTEXT.strip()}

When given a news signal, return a JSON object with exactly these fields:
{{
  "competitor": "<one of: {', '.join(VALID_COMPETITORS)}>",
  "category": "<one of: {', '.join(VALID_CATEGORIES)}>",
  "severity_score": <integer 1-10>,
  "headline": "<cleaned, factual headline, max 120 chars>",
  "summary": "<1 sentence factual summary of the event>",
  "strategic_impact": "<2 sentences: what this means specifically for Aleph Cloud's competitive position>",
  "tags": ["<tag1>", "<tag2>"]
}}

Scoring guide:
- 9-10 (Critical): Major outage affecting EU workloads, competitor achieving sovereign cert, large EU funding round
- 6-8 (High): New GPU region launch, significant pricing change, partnership announcement
- 3-5 (Medium): Minor product update, blog post about roadmap, small funding
- 1-2 (Low): US-only news, non-EU market moves, non-cloud mentions

Return only the JSON object. No explanation or markdown."""

USER_PROMPT = """Signal to analyze:
Title: {title}
Source: {source}
Published: {published}
Body: {body}"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30))
def _call_openai(signal: dict) -> dict | None:
    """Send a signal to OpenAI for analysis. Returns a parsed dict or None."""
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — returning mock analysis")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)

    user_msg = USER_PROMPT.format(
        title=signal.get("raw_title", ""),
        source=signal.get("source", ""),
        published=signal.get("raw_published", ""),
        body=signal.get("raw_body", ""),
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        max_completion_tokens=512,
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    return json.loads(raw)


def _score_to_severity(score: int) -> str:
    if score >= 9:
        return "Critical"
    elif score >= 6:
        return "High"
    elif score >= 3:
        return "Medium"
    return "Low"


def analyze_impact(signals: list[dict] | None = None) -> list[dict]:
    """
    Run LLM analysis on all deduped signals.
    Returns list of CompetitorEvent dicts ready for store_events.py.
    """
    if signals is None:
        if not INPUT_FILE.exists():
            logger.error(f"analyze_impact.py: {INPUT_FILE} not found")
            return []
        signals = json.loads(INPUT_FILE.read_text(encoding='utf-8'))

    logger.info(f"analyze_impact.py: analyzing {len(signals)} signals")
    events = []

    for signal in signals:
        try:
            analysis = _call_openai(signal)

            if analysis is None:
                # Fallback: minimal event without LLM enrichment
                analysis = {
                    "competitor": signal.get("competitor_hint", "Other"),
                    "category": "News",
                    "severity_score": 3,
                    "headline": signal.get("raw_title", "")[:120],
                    "summary": signal.get("raw_body", "")[:200],
                    "strategic_impact": "LLM analysis unavailable — OPENAI_API_KEY not set.",
                    "tags": [],
                }

            severity = _score_to_severity(int(analysis.get("severity_score", 3)))

            event = {
                "id": str(uuid.uuid4()),
                "timestamp": signal.get("raw_published") or datetime.now(timezone.utc).isoformat(),
                "competitor": analysis.get("competitor", "Other"),
                "category": analysis.get("category", "News"),
                "severity": severity,
                "headline": analysis.get("headline", signal.get("raw_title", ""))[:120],
                "summary": analysis.get("summary", ""),
                "source_url": signal.get("raw_url", ""),
                "strategic_impact": analysis.get("strategic_impact", ""),
                "tags": json.dumps(analysis.get("tags", [])),
            }
            events.append(event)
            logger.info(f"  [{severity}] {event['competitor']} / {event['category']}: {event['headline'][:60]}...")

        except Exception as e:
            logger.error(f"  analyze_impact failed for signal '{signal.get('raw_title', '')}': {e}")

    OUTPUT_FILE.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding='utf-8')
    logger.info(f"analyze_impact.py: wrote {len(events)} analyzed events to {OUTPUT_FILE}")
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mock_signal = {
        "source": "rss",
        "competitor_hint": "Scaleway",
        "raw_title": "Scaleway launches H100 cluster in Paris-2 region",
        "raw_url": "https://example.com/scaleway-h100",
        "raw_published": datetime.now(timezone.utc).isoformat(),
        "raw_body": "Scaleway has announced general availability of H100 GPU instances in its Paris-2 datacenter.",
    }
    results = analyze_impact([mock_signal])
    print(json.dumps(results, indent=2))
