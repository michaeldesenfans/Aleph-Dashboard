"""Aleph Dashboard V2 API server."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from server.api.v2 import create_v2_blueprint
from server.config import ADMIN_API_KEY, CORS_ALLOWED_ORIGINS, DASHBOARD_DIR, DISCOVERY_INTERVAL_MINUTES, SERVER_HOST, SERVER_PORT, STATUS_POLL_SECONDS, SYNTHESIS_INTERVAL_MINUTES
from server.pipelines.discovery_pipeline import run_discovery_pipeline
from server.pipelines.orchestrator import run_full_pipeline
from server.pipelines.status_pipeline import run_status_pipeline
from server.read_models.v2 import build_events, build_health
from server.repositories.db import init_db
from server.services.synthesis import ensure_synthesis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aleph.api")

app = Flask(__name__, static_folder=str(DASHBOARD_DIR))
if CORS_ALLOWED_ORIGINS:
    CORS(app, origins=CORS_ALLOWED_ORIGINS)

_pipeline_state = {"last_run": None, "last_summary": None, "running": False}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _legacy_event_shape(item: dict) -> dict:
    event_type = item.get("event_type") or "news"
    category_map = {
        "launch": "Product Launch",
        "funding": "Funding",
        "policy": "Policy",
        "pricing": "News",
        "partnership": "News",
        "outage": "Outage",
        "news": "News",
    }
    return {
        "id": item["id"],
        "timestamp": item.get("detected_at"),
        "competitor": item.get("provider"),
        "category": category_map.get(event_type, "News"),
        "severity": item.get("severity"),
        "headline": item.get("headline"),
        "summary": item.get("summary"),
        "source_url": item.get("source_url"),
        "strategic_impact": item.get("strategic_impact"),
        "tags": item.get("tags", []),
    }


def _run_in_background(target):
    if _pipeline_state["running"]:
        return False

    def _worker():
        _pipeline_state["running"] = True
        try:
            summary = target()
            _pipeline_state["last_summary"] = summary
            _pipeline_state["last_run"] = _now_iso()
        except Exception as exc:
            logger.error("Pipeline task failed: %s", exc)
            _pipeline_state["last_summary"] = {"error": str(exc)}
            _pipeline_state["last_run"] = _now_iso()
        finally:
            _pipeline_state["running"] = False

    threading.Thread(target=_worker, daemon=True).start()
    return True


@app.get("/")
def index():
    return send_from_directory(str(DASHBOARD_DIR), "v2_enhanced.html")


@app.get("/index.html")
def legacy_index():
    return send_from_directory(str(DASHBOARD_DIR), "index.html")


@app.get("/<path:filename>")
def static_assets(filename: str):
    return send_from_directory(str(DASHBOARD_DIR), filename)


@app.post("/api/run")
def trigger_pipeline():
    if not ADMIN_API_KEY:
        return jsonify({"error": "ADMIN_API_KEY not configured"}), 403
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != ADMIN_API_KEY:
        return jsonify({"error": "unauthorized"}), 401
    if not _run_in_background(lambda: run_full_pipeline(trigger_type="manual")):
        return jsonify({"status": "already_running"}), 409
    return jsonify({"status": "started"}), 202


@app.get("/api/status")
def legacy_status():
    return jsonify(build_health(_pipeline_state))


@app.get("/api/events")
def legacy_events():
    competitor = request.args.get("competitor") or None
    category = request.args.get("category") or None
    severity_raw = request.args.get("severity")
    severity = [item.strip() for item in severity_raw.split(",")] if severity_raw else None
    limit = int(request.args.get("limit", 50))
    hours = request.args.get("hours")
    competitor_map = {
        "AWS": "aws",
        "Azure": "azure",
        "GCP": "gcp",
        "OVHcloud": "ovhcloud",
        "Scaleway": "scaleway",
        "Hetzner": "hetzner",
        "DigitalOcean": "digitalocean",
        "CoreWeave": "coreweave",
        "IONOS": "ionos-cloud",
    }
    category_map = {
        "Outage": "outage",
        "Funding": "funding",
        "Product Launch": "launch",
        "Policy": "policy",
        "News": "news",
    }
    payload = build_events(
        competitor=competitor_map.get(competitor) if competitor else None,
        event_type=category_map.get(category) if category else None,
        severity=severity,
        limit=limit,
        hours=int(hours) if hours else None,
    )
    return jsonify(
        {
            "events": [_legacy_event_shape(item) for item in payload["items"]],
            "total": payload["total"],
            "last_updated": _pipeline_state.get("last_run"),
            "pipeline": {
                "last_run": _pipeline_state.get("last_run"),
                "running": _pipeline_state.get("running", False),
            },
        }
    )


def _scheduled_status():
    if not _pipeline_state["running"]:
        run_status_pipeline(trigger_type="scheduled")


def _scheduled_discovery():
    if not _pipeline_state["running"]:
        run_discovery_pipeline(trigger_type="scheduled")
        ensure_synthesis()


def _scheduled_synthesis():
    ensure_synthesis()


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(_scheduled_status, "interval", seconds=STATUS_POLL_SECONDS, id="status", replace_existing=True)
    scheduler.add_job(_scheduled_discovery, "interval", minutes=DISCOVERY_INTERVAL_MINUTES, id="discovery", replace_existing=True)
    scheduler.add_job(_scheduled_synthesis, "interval", minutes=SYNTHESIS_INTERVAL_MINUTES, id="synthesis", replace_existing=True)
    scheduler.start()
    return scheduler


def create_app():
    init_db()
    app.register_blueprint(create_v2_blueprint(_pipeline_state))
    return app


create_app()


if __name__ == "__main__":
    scheduler = start_scheduler()
    logger.info("Aleph Dashboard V2 starting on http://%s:%s", SERVER_HOST, SERVER_PORT)
    try:
        app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, use_reloader=False)
    finally:
        scheduler.shutdown()
