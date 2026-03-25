"""Broader intelligence discovery pipeline using feeds plus selective Brave queries."""

from __future__ import annotations

import logging

from server.adapters.brave_adapter import BraveAdapter, BraveBudgetExceeded
from server.adapters.feed_adapter import fetch_feed
from server.config import BRAVE_MAX_MONTHLY_CALLS, BRAVE_QUERY_LIMIT_PER_RUN, DOCUMENT_BATCH_SIZE
from server.repositories.competitors import get_source_endpoints, update_endpoint_check
from server.repositories.discovery import finish_run, get_due_queries, log_run, mark_query_run
from server.repositories.documents import get_pending_documents, insert_document, url_exists
from server.services.budget import BraveBudgetManager
from server.services.extraction import extract_and_store_events

logger = logging.getLogger(__name__)


def _ingest_pinned_sources(stats: dict):
    endpoints = get_source_endpoints(enabled_only=True, pinned_only=True)
    news_like = [endpoint for endpoint in endpoints if endpoint["purpose"] in ("news", "press", "releases")]
    for endpoint in news_like:
        if endpoint["adapter_type"] != "rss":
            continue
        try:
            documents = fetch_feed(endpoint["endpoint_url"], max_items=6)
            stats["feed_checks"] += 1
            for doc in documents:
                if not doc.get("url") or url_exists(doc["url"]):
                    stats["docs_skipped"] += 1
                    continue
                doc["source_endpoint_id"] = endpoint["id"]
                insert_document(doc)
                stats["docs_ingested"] += 1
            update_endpoint_check(endpoint["id"], success=True)
        except Exception as exc:
            stats["errors"] += 1
            update_endpoint_check(endpoint["id"], success=False, error_msg=str(exc)[:200])
            logger.error("Feed ingestion failed for %s: %s", endpoint["endpoint_url"], exc)


def _run_brave_queries(stats: dict):
    budget = BraveBudgetManager()
    if not budget.can_run_query():
        return

    adapter = BraveAdapter(max_monthly_calls=BRAVE_MAX_MONTHLY_CALLS)
    queries = get_due_queries(limit=BRAVE_QUERY_LIMIT_PER_RUN)
    for query in queries:
        if not budget.can_run_query():
            break
        try:
            if query["endpoint_type"] == "web":
                results = adapter.search_web(query["query_template"], count=query["count"], freshness=query["freshness_window"])
            else:
                results = adapter.search_news(query["query_template"], count=query["count"], freshness=query["freshness_window"])
            mark_query_run(query["id"], result_count=len(results))
            stats["brave_queries"] += 1
            for result in results:
                if not result.get("url") or url_exists(result["url"]):
                    stats["docs_skipped"] += 1
                    continue
                result["discovery_query_id"] = query["id"]
                insert_document(result)
                stats["docs_ingested"] += 1
        except BraveBudgetExceeded:
            logger.warning("Brave budget exhausted; ending discovery sweep")
            break
        except Exception as exc:
            stats["errors"] += 1
            logger.error("Brave query failed: %s", exc)


def _extract_pending_documents(stats: dict):
    pending = get_pending_documents(limit=DOCUMENT_BATCH_SIZE)
    if not pending:
        return
    stats["docs_extracted"] = len(pending)
    stats["events_created"] = extract_and_store_events(pending)


def run_discovery_pipeline(trigger_type: str = "scheduled") -> dict:
    run_id = log_run("discovery", trigger_type)
    stats = {
        "feed_checks": 0,
        "brave_queries": 0,
        "docs_ingested": 0,
        "docs_skipped": 0,
        "docs_extracted": 0,
        "events_created": 0,
        "errors": 0,
    }
    try:
        _ingest_pinned_sources(stats)
        _run_brave_queries(stats)
        _extract_pending_documents(stats)
        finish_run(run_id, "completed", stats)
        logger.info("Discovery pipeline complete: %s", stats)
        return stats
    except Exception as exc:
        finish_run(run_id, "failed", stats, str(exc))
        logger.error("Discovery pipeline failed: %s", exc)
        return stats
