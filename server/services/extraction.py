"""OpenAI-backed document extraction into canonical events."""

from __future__ import annotations

import json
import logging
import re

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from server.config import OPENAI_API_KEY, OPENAI_MODEL
from server.repositories.competitors import get_competitor_id_map
from server.repositories.documents import update_document_status
from server.repositories.events import insert_event, link_evidence

logger = logging.getLogger(__name__)

COMPETITOR_SLUGS = [
    "aws",
    "azure",
    "gcp",
    "oracle-cloud",
    "coreweave",
    "alibaba-cloud",
    "ovhcloud",
    "scaleway",
    "open-telekom-cloud",
    "ionos-cloud",
    "digitalocean",
    "akamai-linode",
    "vultr",
    "hetzner",
    "ibm-cloud",
    "crusoe",
    "lambda-labs",
    "unknown",
]

EVENT_TYPES = ["outage", "launch", "funding", "policy", "partnership", "pricing", "news"]

ALEPH_CONTEXT = """Aleph Cloud is a European cloud infrastructure startup serving teams that outgrow
simple developer clouds and need EU-native production infra, GPUs, and sovereign compliance paths.
Aleph competes on transparent pricing, developer experience, EU legal posture, and data residency."""

EXTRACTION_PROMPT = f"""You are a competitive intelligence extraction engine for Aleph Cloud.

Context:
{ALEPH_CONTEXT}

Given a retrieved document, decide whether it is relevant to cloud infrastructure competition.
Return JSON only using this schema:
{{
  "reject": false,
  "competitor_slug": "<one of {', '.join(COMPETITOR_SLUGS)}>",
  "event_type": "<one of {', '.join(EVENT_TYPES)}>",
  "title": "<clean factual title, max 120 chars>",
  "summary": "<1 sentence factual summary>",
  "strategic_impact": "<1-2 sentences about what this means for Aleph Cloud>",
  "severity_score": <1-10 integer>,
  "confidence": <0.0-1.0>,
  "tags": ["tag1", "tag2"],
  "region": "<region or null>"
}}

If irrelevant, return:
{{"reject": true, "reason": "why irrelevant"}}
"""


def _heuristic_event_type(title: str, body: str) -> str:
    text = f"{title} {body}".lower()
    if any(token in text for token in ("outage", "degraded", "incident", "latency")):
        return "outage"
    if any(token in text for token in ("funding", "raised", "investment", "earnings", "revenue")):
        return "funding"
    if any(token in text for token in ("partnership", "alliance", "integrat")):
        return "partnership"
    if any(token in text for token in ("pricing", "price", "discount", "free tier")):
        return "pricing"
    if any(token in text for token in ("regulation", "compliance", "secnumcloud", "eucs", "c5", "sovereign")):
        return "policy"
    if any(token in text for token in ("launch", "ga", "region", "gpu", "datacenter", "instance")):
        return "launch"
    return "news"


def _heuristic_tags(title: str, body: str) -> list[str]:
    text = f"{title} {body}".lower()
    tags = []
    for token, label in (
        ("gpu", "GPU"),
        ("ai", "AI"),
        ("secnumcloud", "SecNumCloud"),
        ("sovereign", "Sovereignty"),
        ("pricing", "Pricing"),
        ("partnership", "Partnership"),
        ("outage", "Reliability"),
    ):
        if token in text:
            tags.append(label)
    return tags[:4]


def _normalize_score(score: int) -> str:
    if score >= 9:
        return "Critical"
    if score >= 6:
        return "High"
    if score >= 3:
        return "Medium"
    return "Low"


def _is_promising_document(document: dict) -> bool:
    title = (document.get("title_raw") or "").strip()
    body = (document.get("snippet_raw") or document.get("content_raw") or "").strip()
    if not title or len(title) < 8:
        return False
    if re.search(r"\b(weather|sports|gaming keyboard|stock photo)\b", f"{title} {body}", re.I):
        return False
    return True


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=15))
def _call_openai(title: str, snippet: str, source_name: str) -> dict | None:
    if not OPENAI_API_KEY:
        return None
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": f"Title: {title}\nSource: {source_name}\nContent: {snippet[:1600]}"},
        ],
        max_completion_tokens=500,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content.strip())


def extract_and_store_events(documents: list[dict]) -> int:
    slug_to_id = get_competitor_id_map()
    created = 0

    for doc in documents:
        doc_id = doc["id"]
        title = doc.get("title_raw", "")
        snippet = doc.get("snippet_raw") or doc.get("content_raw") or ""
        source_name = doc.get("source_name", "")
        hinted_slug = doc.get("competitor_slug")

        if not _is_promising_document(doc):
            update_document_status(doc_id, "rejected", "low-signal")
            continue

        try:
            result = _call_openai(title, snippet, source_name)
            if result is None:
                guessed_type = _heuristic_event_type(title, snippet)
                score = 6 if guessed_type in ("launch", "policy", "funding", "outage") else 4
                result = {
                    "competitor_slug": hinted_slug or "unknown",
                    "event_type": guessed_type,
                    "title": title[:120],
                    "summary": snippet[:220],
                    "strategic_impact": "Structured extraction unavailable; event stored with heuristic fallback.",
                    "severity_score": score,
                    "confidence": 0.35,
                    "tags": _heuristic_tags(title, snippet),
                    "region": None,
                }

            if result.get("reject"):
                update_document_status(doc_id, "rejected", result.get("reason", "irrelevant"))
                continue

            competitor_slug = result.get("competitor_slug") or hinted_slug or "unknown"
            if competitor_slug == "unknown" and hinted_slug:
                competitor_slug = hinted_slug
            score = int(result.get("severity_score", 3))

            event_id = insert_event(
                {
                    "event_key": f"doc-{doc_id}",
                    "event_type": result.get("event_type", "news"),
                    "competitor_id": slug_to_id.get(competitor_slug),
                    "title": (result.get("title") or title)[:120],
                    "summary": result.get("summary") or snippet[:220],
                    "strategic_impact": result.get("strategic_impact", ""),
                    "severity_score": score,
                    "severity_label": _normalize_score(score),
                    "confidence": float(result.get("confidence", 0.5)),
                    "started_at": doc.get("published_at"),
                    "primary_region": result.get("region"),
                    "tags": result.get("tags", []),
                    "metadata": {
                        "source_name": source_name,
                        "source_url": doc.get("url"),
                        "document_id": doc_id,
                    },
                }
            )
            if event_id > 0:
                link_evidence(event_id, doc_id, "source", float(result.get("confidence", 0.5)))
                created += 1
            update_document_status(doc_id, "processed")
        except Exception as exc:
            logger.error("Extraction failed for doc %s: %s", doc_id, exc)
            update_document_status(doc_id, "pending", str(exc)[:200])

    logger.info("Extraction complete: %s events created from %s documents", created, len(documents))
    return created
