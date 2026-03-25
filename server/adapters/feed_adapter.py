"""RSS/Atom feed adapter for pinned blog/press sources."""

import logging
import feedparser
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def fetch_feed(endpoint_url: str, max_items: int = 10) -> list[dict]:
    """Parse an RSS/Atom feed and return normalized document dicts."""
    try:
        feed = feedparser.parse(endpoint_url)
        results = []
        for entry in feed.entries[:max_items]:
            published = entry.get("published", entry.get("updated", ""))
            body = entry.get("summary", "")
            if not body and entry.get("content"):
                body = entry["content"][0].get("value", "")

            results.append({
                "url": entry.get("link", ""),
                "title_raw": entry.get("title", ""),
                "snippet_raw": body[:500] if body else "",
                "published_at": published,
                "source_name": feed.feed.get("title", ""),
                "content_raw": body[:2000] if body else "",
            })
        return results
    except Exception as e:
        logger.error(f"Feed fetch failed for {endpoint_url}: {e}")
        return []
