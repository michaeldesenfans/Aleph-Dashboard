"""
Tool: fetch_news.py
Layer: 3 — Execution
SOP: architecture/competitive_monitoring_sop.md

Fetches raw competitive news signals from:
  1. NewsAPI.org (primary)
  2. RSS feeds (backup / supplement)

Output: .tmp/raw_news.json — list of RawSignal objects
"""

import os
import json
import time
import random
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
import feedparser
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger(__name__)

TMP_DIR = ROOT / ".tmp"
TMP_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = TMP_DIR / "raw_news.json"

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_BASE = "https://newsapi.org/v2/everything"

# --- Competitor query terms for NewsAPI ---
NEWSAPI_QUERIES = [
    ("AWS",          '"AWS" OR "Amazon Web Services" cloud EU'),
    ("Azure",        '"Azure" OR "Microsoft Cloud" EU sovereign'),
    ("GCP",          '"Google Cloud" OR "GCP" EU cloud'),
    ("OVHcloud",     '"OVHcloud" OR "OVH" cloud'),
    ("Scaleway",     '"Scaleway" OR "Iliad cloud"'),
    ("Hetzner",      '"Hetzner" cloud'),
    ("DigitalOcean", '"DigitalOcean" cloud'),
    ("CoreWeave",    '"CoreWeave"'),
    ("IONOS",        '"IONOS cloud"'),
]

# --- RSS feed URLs (backup / supplement) ---
RSS_FEEDS = [
    ("AWS",          "https://aws.amazon.com/blogs/aws/feed/"),
    ("Azure",        "https://azure.microsoft.com/en-us/blog/feed/"),
    ("GCP",          "https://cloud.google.com/feeds/gcp-release-notes.xml"),
    ("Hetzner",      "https://www.hetzner.com/news/feed.rss"),
    ("OVHcloud",     "https://blog.ovhcloud.com/feed/"),
    ("General",      "https://thenewstack.io/feed/"),
    ("General",      "https://venturebeat.com/category/ai/feed/"),
]


def _build_raw_signal(competitor: str, title: str, url: str, published: str, body: str) -> dict:
    return {
        "source": "newsapi",
        "competitor_hint": competitor,
        "raw_title": title,
        "raw_url": url,
        "raw_published": published,
        "raw_body": body[:500] if body else "",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_newsapi(competitor: str, query: str) -> list[dict]:
    """Fetch articles from NewsAPI for a single query term."""
    if not NEWS_API_KEY:
        logger.warning("NEWS_API_KEY not set — skipping NewsAPI fetch")
        return []

    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": NEWS_API_KEY,
    }

    resp = requests.get(NEWS_API_BASE, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    signals = []
    for article in data.get("articles", []):
        signals.append(_build_raw_signal(
            competitor=competitor,
            title=article.get("title", ""),
            url=article.get("url", ""),
            published=article.get("publishedAt", datetime.now(timezone.utc).isoformat()),
            body=article.get("description", "") or article.get("content", ""),
        ))

    # Jitter to stay within rate limits
    time.sleep(random.uniform(1.0, 3.0))
    return signals


def _fetch_rss(competitor: str, feed_url: str) -> list[dict]:
    """Fetch articles from an RSS/Atom feed."""
    try:
        feed = feedparser.parse(feed_url)
        signals = []
        for entry in feed.entries[:5]:  # Cap at 5 per feed
            published = entry.get("published", datetime.now(timezone.utc).isoformat())
            body = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
            signals.append({
                "source": "rss",
                "competitor_hint": competitor,
                "raw_title": entry.get("title", ""),
                "raw_url": entry.get("link", ""),
                "raw_published": published,
                "raw_body": body[:500],
            })
        return signals
    except Exception as e:
        logger.error(f"RSS fetch failed for {feed_url}: {e}")
        return []


def fetch_signals() -> list[dict]:
    """
    Fetch all competitive news signals from NewsAPI and RSS feeds.
    Returns a list of RawSignal dicts written to .tmp/raw_news.json.
    """
    logger.info("fetch_news.py: starting signal ingestion")
    all_signals = []

    # 1. NewsAPI
    for competitor, query in NEWSAPI_QUERIES:
        try:
            signals = _fetch_newsapi(competitor, query)
            all_signals.extend(signals)
            logger.info(f"  NewsAPI [{competitor}]: {len(signals)} signals")
        except Exception as e:
            logger.error(f"  NewsAPI [{competitor}] failed: {e}")

    # 2. RSS feeds
    for competitor, feed_url in RSS_FEEDS:
        signals = _fetch_rss(competitor, feed_url)
        all_signals.extend(signals)
        logger.info(f"  RSS [{competitor}]: {len(signals)} signals")

    # Write to .tmp
    OUTPUT_FILE.write_text(json.dumps(all_signals, indent=2, ensure_ascii=False), encoding='utf-8')
    logger.info(f"fetch_news.py: wrote {len(all_signals)} signals to {OUTPUT_FILE}")
    return all_signals


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    signals = fetch_signals()
    print(f"Captured {len(signals)} raw news signals.")
