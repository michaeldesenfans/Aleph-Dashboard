"""V2 API route registration."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from server.read_models.v2 import (
    build_csp_status,
    build_events,
    build_headlines,
    build_health,
    build_momentum,
    build_signals,
    build_stats,
    build_trend,
    build_trend_article,
    build_trend_chart_data,
)


def create_v2_blueprint(pipeline_state: dict):
    bp = Blueprint("api_v2", __name__, url_prefix="/api/v2")

    @bp.get("/stats")
    def stats():
        return jsonify(build_stats(pipeline_state))

    @bp.get("/csp-status")
    def csp_status():
        return jsonify(build_csp_status())

    @bp.get("/headlines")
    def headlines():
        return jsonify(build_headlines())

    @bp.get("/events")
    def events():
        competitor = request.args.get("competitor") or None
        event_type = request.args.get("event_type") or None
        severity_raw = request.args.get("severity")
        severity = [item.strip() for item in severity_raw.split(",")] if severity_raw else None
        limit = int(request.args.get("limit", 30))
        hours = request.args.get("hours")
        return jsonify(
            build_events(
                competitor=competitor,
                event_type=event_type,
                severity=severity,
                limit=limit,
                hours=int(hours) if hours else None,
            )
        )

    @bp.get("/momentum")
    def momentum():
        window = request.args.get("window", "30d")
        return jsonify(build_momentum(window=window))

    @bp.get("/synthesis/trend")
    def trend():
        return jsonify(build_trend())

    @bp.get("/synthesis/trend/article")
    def trend_article():
        return jsonify(build_trend_article())

    @bp.get("/synthesis/trend/chart-data")
    def trend_chart_data():
        return jsonify(build_trend_chart_data())

    @bp.get("/synthesis/signals")
    def signals():
        return jsonify(build_signals())

    @bp.get("/health")
    def health():
        return jsonify(build_health(pipeline_state))

    return bp
