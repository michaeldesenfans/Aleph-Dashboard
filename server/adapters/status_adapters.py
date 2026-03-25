"""Adapters for fetching and parsing provider status pages."""

from __future__ import annotations

import json
import logging

import feedparser
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "AlephDashboard/2.0"}


def _endpoint_url(endpoint: dict) -> str:
    return endpoint["endpoint_url"]


def _parser_config(endpoint: dict) -> dict:
    raw = endpoint.get("parser_config_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def _get(url: str, *, timeout: int = 10, verify: bool = True) -> requests.Response:
    return requests.get(url, timeout=timeout, headers=HEADERS, verify=verify)


def parse_atlassian_v2(endpoint: dict) -> list[dict]:
    config = _parser_config(endpoint)
    resp = _get(_endpoint_url(endpoint), verify=config.get("verify_ssl", True))
    resp.raise_for_status()
    data = resp.json()
    incidents = []
    for inc in data.get("incidents", [])[:10]:
        status = inc.get("status", "investigating")
        resolved = status in ("resolved", "postmortem")
        updates = inc.get("incident_updates", [])
        summary = updates[0].get("body", "") if updates else ""
        incidents.append(
            {
                "external_incident_id": inc.get("id") or inc.get("shortlink") or inc.get("name"),
                "title": inc.get("name", "Unknown incident"),
                "summary": summary[:500],
                "status": "resolved" if resolved else ("degraded" if status == "degraded_performance" else "active"),
                "severity": {"critical": "critical", "major": "major", "minor": "minor", "none": "minor"}.get(inc.get("impact", "none"), "minor"),
                "incident_url": inc.get("shortlink", ""),
                "affected_services": [comp.get("name", "") for comp in inc.get("components", [])],
                "started_at": inc.get("created_at"),
                "resolved_at": inc.get("resolved_at"),
            }
        )
    return incidents


def parse_statuspage_status_json(endpoint: dict) -> list[dict]:
    config = _parser_config(endpoint)
    resp = _get(_endpoint_url(endpoint), verify=config.get("verify_ssl", True))
    resp.raise_for_status()
    data = resp.json()
    status = (data.get("status") or {}).get("indicator", "none")
    description = (data.get("status") or {}).get("description", "Operational")
    if status == "none":
        return []
    return [
        {
            "external_incident_id": f"status::{description}",
            "title": description,
            "summary": description,
            "status": "degraded" if status == "minor" else "active",
            "severity": "major" if status in ("minor", "major") else "critical",
            "incident_url": _endpoint_url(endpoint).rsplit("/", 1)[0],
            "affected_services": [],
            "started_at": None,
            "resolved_at": None,
        }
    ]


def parse_gcp_incidents(endpoint: dict) -> list[dict]:
    config = _parser_config(endpoint)
    resp = _get(_endpoint_url(endpoint), verify=config.get("verify_ssl", True))
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        data = []
    incidents = []
    for inc in data[:10]:
        resolved = bool(inc.get("end"))
        severity_text = inc.get("severity", "low")
        incidents.append(
            {
                "external_incident_id": inc.get("id", str(inc.get("number", ""))),
                "title": inc.get("external_desc", "GCP incident"),
                "summary": inc.get("external_desc", ""),
                "status": "resolved" if resolved else "active",
                "severity": {"high": "critical", "medium": "major"}.get(severity_text, "minor"),
                "incident_url": inc.get("uri", "https://status.cloud.google.com"),
                "affected_services": [item.get("title", "") for item in inc.get("affected_products", [])],
                "started_at": inc.get("begin"),
                "resolved_at": inc.get("end"),
            }
        )
    return incidents


def parse_rss_status(endpoint: dict) -> list[dict]:
    feed = feedparser.parse(_endpoint_url(endpoint))
    incidents = []
    for entry in feed.entries[:10]:
        title = entry.get("title", "Status update")
        summary = entry.get("summary", "")
        link = entry.get("link", _endpoint_url(endpoint))
        published = entry.get("published", "")
        title_lower = title.lower()
        if any(word in title_lower for word in ("resolved", "completed", "recovered", "restored", "operational")):
            status = "resolved"
        elif any(word in title_lower for word in ("degraded", "delay", "intermittent", "elevated")):
            status = "degraded"
        else:
            status = "active"
        incidents.append(
            {
                "external_incident_id": f"{link}::{published}::{title}",
                "title": title,
                "summary": summary[:500],
                "status": status,
                "severity": "minor",
                "incident_url": link,
                "affected_services": [],
                "started_at": published,
                "resolved_at": published if status == "resolved" else None,
            }
        )
    return incidents


def parse_aws_health_rss(endpoint: dict) -> list[dict]:
    feed = feedparser.parse(_endpoint_url(endpoint))
    incidents = []
    for entry in feed.entries[:10]:
        title = entry.get("title", "AWS status update")
        summary = entry.get("summary", "")
        link = entry.get("link", "https://status.aws.amazon.com")
        title_lower = title.lower()
        if any(word in title_lower for word in ("resolved", "recovered", "operational")):
            status = "resolved"
        elif any(word in title_lower for word in ("degraded", "elevated", "increased")):
            status = "degraded"
        else:
            status = "active"
        incidents.append(
            {
                "external_incident_id": f"{link}::{entry.get('published', '')}::{title}",
                "title": title,
                "summary": summary[:500],
                "status": status,
                "severity": "major" if "elevated" in title_lower or "increased" in title_lower else "minor",
                "incident_url": link,
                "affected_services": [],
                "started_at": entry.get("published", ""),
                "resolved_at": None if status != "resolved" else entry.get("published", ""),
            }
        )
    return incidents


def parse_vultr_status_json(endpoint: dict) -> list[dict]:
    config = _parser_config(endpoint)
    resp = _get(_endpoint_url(endpoint), verify=config.get("verify_ssl", True))
    resp.raise_for_status()
    data = resp.json()
    incidents = []
    for alert in data.get("service_alerts", []):
        status_raw = (alert.get("status") or "").lower()
        resolved = status_raw in ("resolved", "completed")
        if resolved:
            status = "resolved"
        elif status_raw in ("degraded", "monitoring"):
            status = "degraded"
        else:
            status = "active"
        incidents.append(
            {
                "external_incident_id": str(alert.get("id", "")),
                "title": alert.get("subject", "Vultr status update"),
                "summary": (alert.get("entries", [{}])[0].get("text", "") if alert.get("entries") else "")[:500],
                "status": status,
                "severity": "major" if status == "active" else "minor",
                "incident_url": "https://status.vultr.com",
                "affected_services": [],
                "started_at": alert.get("start_date"),
                "resolved_at": alert.get("end_date"),
            }
        )
    return incidents


ADAPTER_MAP = {
    "atlassian_v2": parse_atlassian_v2,
    "statuspage_status_json": parse_statuspage_status_json,
    "gcp_incidents": parse_gcp_incidents,
    "rss": parse_rss_status,
    "aws_health_rss": parse_aws_health_rss,
    "vultr_status_json": parse_vultr_status_json,
}


def fetch_status(endpoint: dict) -> list[dict]:
    adapter = ADAPTER_MAP.get(endpoint["adapter_type"])
    if not adapter:
        logger.warning("No adapter for status source type %s", endpoint["adapter_type"])
        return []
    return adapter(endpoint)
