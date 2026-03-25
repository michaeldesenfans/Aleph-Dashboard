"""Fast authoritative provider status polling pipeline."""

from __future__ import annotations

import logging

from server.adapters.status_adapters import fetch_status
from server.repositories.competitors import get_pinned_competitors, get_source_endpoints, update_endpoint_check
from server.repositories.discovery import finish_run, log_run
from server.repositories.events import insert_incident
from server.repositories.status import mark_provider_checked, set_provider_unknown, update_provider_status

logger = logging.getLogger(__name__)


def run_status_pipeline(trigger_type: str = "scheduled") -> dict:
    run_id = log_run("status", trigger_type)
    stats = {"providers_checked": 0, "endpoints_checked": 0, "incidents_seen": 0, "errors": 0}

    competitors = {row["id"]: row for row in get_pinned_competitors()}
    endpoints = get_source_endpoints(purpose="status", pinned_only=True)
    by_competitor: dict[int, list[dict]] = {}
    for endpoint in endpoints:
        by_competitor.setdefault(endpoint["competitor_id"], []).append(endpoint)

    try:
        for competitor_id, competitor in competitors.items():
            stats["providers_checked"] += 1
            endpoint_group = by_competitor.get(competitor_id, [])
            if not endpoint_group:
                set_provider_unknown(competitor_id, source_coverage="none")
                continue

            all_incidents: list[dict] = []
            endpoint_errors = 0
            for endpoint in endpoint_group:
                try:
                    incidents = fetch_status(endpoint)
                    stats["endpoints_checked"] += 1
                    update_endpoint_check(endpoint["id"], success=True)
                    for incident in incidents:
                        incident["competitor_id"] = competitor_id
                        incident["source_endpoint_id"] = endpoint["id"]
                        insert_incident(incident)
                    stats["incidents_seen"] += len(incidents)
                    all_incidents.extend(incidents)
                except Exception as exc:
                    endpoint_errors += 1
                    stats["errors"] += 1
                    update_endpoint_check(endpoint["id"], success=False, error_msg=str(exc)[:200])
                    logger.error("Status endpoint failed for %s: %s", competitor["slug"], exc)

            if endpoint_errors == len(endpoint_group):
                set_provider_unknown(competitor_id, source_coverage="partial")
                continue

            active = [item for item in all_incidents if item.get("status") == "active"]
            degraded = [item for item in all_incidents if item.get("status") in ("degraded", "monitoring")]
            if active:
                state = "outage"
            elif degraded:
                state = "degraded"
            else:
                state = "clear"

            if all_incidents:
                update_provider_status(
                    competitor_id=competitor_id,
                    state=state,
                    incidents=sorted(
                        all_incidents,
                        key=lambda incident: str(incident.get("started_at") or incident.get("resolved_at") or ""),
                        reverse=True,
                    ),
                    source_endpoint_id=endpoint_group[0]["id"],
                    source_coverage="full",
                )
            else:
                mark_provider_checked(competitor_id, source_coverage="full")
                update_provider_status(
                    competitor_id=competitor_id,
                    state="clear",
                    incidents=[],
                    source_endpoint_id=endpoint_group[0]["id"],
                    source_coverage="full",
                )

        finish_run(run_id, "completed", stats)
        return stats
    except Exception as exc:
        finish_run(run_id, "failed", stats, str(exc))
        logger.error("Status pipeline failed: %s", exc)
        return stats
