"""
Tool: fetch_status_pages.py
Layer: 3 — Execution
SOP: architecture/competitive_monitoring_sop.md

Polls competitor infrastructure status pages for active incidents/outages.

Output: .tmp/raw_status.json — list of RawSignal objects (source: "statuspage")
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
import feedparser
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
TMP_DIR = ROOT / ".tmp"
TMP_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = TMP_DIR / "raw_status.json"


# --- Status page configurations per provider ---
# Each entry: (competitor, type, url)
# type: "json_atlassian" | "json_aws" | "json_gcp" | "rss"
STATUS_PAGES = [
    ("AWS",          "json_aws",        "https://status.aws.amazon.com/data.json"),
    ("Azure",        "rss",             "https://azure.status.microsoft/en-us/status/feed/"),
    ("GCP",          "json_gcp",        "https://status.cloud.google.com/incidents.json"),
    ("Hetzner",      "rss",             "https://www.hetzner-status.de/en.atom"),
    ("DigitalOcean", "rss",             "https://status.digitalocean.com/history.rss"),
    ("OVHcloud",     "rss",             "https://travaux.ovh.net/?do=rss"),
    ("Scaleway",     "json_atlassian",  "https://status.scaleway.com/api/v2/incidents.json"),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_signal(competitor: str, title: str, url: str, published: str, body: str) -> dict:
    return {
        "source": "statuspage",
        "competitor_hint": competitor,
        "raw_title": title,
        "raw_url": url,
        "raw_published": published,
        "raw_body": body[:500],
    }


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
def _get(url: str, timeout: int = 10) -> requests.Response:
    return requests.get(url, timeout=timeout, headers={"User-Agent": "AlephDashboard/2.0"})


def _parse_atlassian(competitor: str, data: dict) -> list[dict]:
    """Parse Atlassian Statuspage API v2 incidents.json format."""
    signals = []
    for incident in data.get("incidents", [])[:5]:
        if incident.get("status") in ("resolved", "postmortem"):
            continue  # Only active incidents
        title = incident.get("name", "Unknown incident")
        url = incident.get("shortlink", "") or incident.get("incident_updates", [{}])[0].get("body", "")
        published = incident.get("created_at", _now_iso())
        body = " | ".join(
            u.get("body", "") for u in incident.get("incident_updates", [])[:2]
        )
        signals.append(_make_signal(competitor, title, url, published, body))
    return signals


def _parse_aws(competitor: str, data: dict) -> list[dict]:
    """Parse AWS status data.json format."""
    # TODO: AWS status JSON format — implement when API structure confirmed
    # Ref: https://status.aws.amazon.com/data.json
    logger.warning("_parse_aws: not yet implemented — skipping")
    return []


def _parse_gcp(competitor: str, data: list) -> list[dict]:
    """Parse GCP incidents.json format (list of incident objects)."""
    signals = []
    for incident in data[:5]:
        if incident.get("end"):  # Resolved
            continue
        title = incident.get("external_desc", "GCP incident")
        url = incident.get("uri", "https://status.cloud.google.com")
        published = incident.get("begin", _now_iso())
        signals.append(_make_signal(competitor, title, url, published, title))
    return signals


def _parse_rss(competitor: str, feed_url: str) -> list[dict]:
    """Parse RSS-based status pages."""
    try:
        feed = feedparser.parse(feed_url)
        signals = []
        for entry in feed.entries[:3]:
            signals.append(_make_signal(
                competitor=competitor,
                title=entry.get("title", "Status update"),
                url=entry.get("link", feed_url),
                published=entry.get("published", _now_iso()),
                body=entry.get("summary", ""),
            ))
        return signals
    except Exception as e:
        logger.error(f"RSS status parse failed for {competitor}: {e}")
        return []


def fetch_status_signals() -> list[dict]:
    """
    Poll all configured status pages and return active incident signals.
    Writes results to .tmp/raw_status.json.
    """
    logger.info("fetch_status_pages.py: polling status pages")
    all_signals = []

    for competitor, page_type, url in STATUS_PAGES:
        try:
            if page_type == "rss":
                signals = _parse_rss(competitor, url)
            else:
                resp = _get(url)
                resp.raise_for_status()
                data = resp.json()

                if page_type == "json_atlassian":
                    signals = _parse_atlassian(competitor, data)
                elif page_type == "json_aws":
                    signals = _parse_aws(competitor, data)
                elif page_type == "json_gcp":
                    signals = _parse_gcp(competitor, data if isinstance(data, list) else [])
                else:
                    signals = []

            all_signals.extend(signals)
            logger.info(f"  StatusPage [{competitor}]: {len(signals)} active incidents")

        except Exception as e:
            logger.error(f"  StatusPage [{competitor}] failed: {e}")

    OUTPUT_FILE.write_text(json.dumps(all_signals, indent=2, ensure_ascii=False), encoding='utf-8')
    logger.info(f"fetch_status_pages.py: wrote {len(all_signals)} signals to {OUTPUT_FILE}")
    return all_signals


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    signals = fetch_status_signals()
    print(f"Captured {len(signals)} active status incidents.")
