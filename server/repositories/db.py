"""Database connection manager and initialization."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from server.config import DB_PATH
from server.models.schema import SCHEMA_SQL
from server.seeds.competitors import COMPETITORS, SOURCE_ENDPOINTS, build_discovery_queries

logger = logging.getLogger(__name__)

_db_path: Path = DB_PATH


def set_db_path(path: Path):
    global _db_path
    _db_path = path


def get_conn() -> sqlite3.Connection:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    # Split schema into individual statements
    statements = [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]
    # Run non-unique-index statements first
    for stmt in statements:
        if "CREATE UNIQUE INDEX" in stmt:
            continue
        try:
            conn.execute(stmt)
        except Exception:
            pass
    conn.commit()
    # Clean duplicates before applying unique indexes
    _dedupe_registry_tables(conn)
    # Now apply unique indexes safely
    for stmt in statements:
        if "CREATE UNIQUE INDEX" not in stmt:
            continue
        try:
            conn.execute(stmt)
        except Exception:
            pass  # Index already exists or data still has issues
    conn.commit()
    _sync_seed_registry(conn)
    conn.close()


def _dedupe_registry_tables(conn: sqlite3.Connection):
    conn.execute(
        """
        DELETE FROM source_endpoints
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM source_endpoints
            GROUP BY competitor_id, source_kind, purpose, endpoint_url
        )
        """
    )
    conn.execute(
        """
        DELETE FROM discovery_queries
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM discovery_queries
            GROUP BY COALESCE(competitor_id, -1), provider, query_family, endpoint_type, query_template
        )
        """
    )
    conn.commit()


def _sync_seed_registry(conn: sqlite3.Connection):
    for competitor in COMPETITORS:
        conn.execute(
            """
            INSERT OR IGNORE INTO competitors
                (slug, name, provider_type, display_order, is_pinned,
                 track_outages, track_news, track_strategy, active, metadata_json)
            VALUES (?, ?, ?, ?, 1, 1, 1, 1, 1, ?)
            """,
            (
                competitor["slug"],
                competitor["name"],
                competitor["provider_type"],
                competitor["display_order"],
                json.dumps({"tier": competitor["tier"]}),
            ),
        )
        conn.execute(
            """
            UPDATE competitors
            SET name = ?, provider_type = ?, display_order = ?, is_pinned = 1,
                track_outages = 1, track_news = 1, track_strategy = 1, active = 1,
                metadata_json = ?, updated_at = datetime('now')
            WHERE slug = ?
            """,
            (
                competitor["name"],
                competitor["provider_type"],
                competitor["display_order"],
                json.dumps({"tier": competitor["tier"]}),
                competitor["slug"],
            ),
        )

    slug_to_id = {
        row["slug"]: row["id"]
        for row in conn.execute("SELECT id, slug FROM competitors").fetchall()
    }

    seeded_endpoint_keys = set()
    for slug, endpoints in SOURCE_ENDPOINTS.items():
        comp_id = slug_to_id.get(slug)
        if not comp_id:
            continue
        for ep in endpoints:
            key = (comp_id, ep["endpoint_url"], ep["purpose"], ep["source_kind"])
            seeded_endpoint_keys.add(key)
            existing_endpoint = conn.execute(
                """
                SELECT id FROM source_endpoints
                WHERE competitor_id = ? AND endpoint_url = ? AND purpose = ? AND source_kind = ?
                """,
                (comp_id, ep["endpoint_url"], ep["purpose"], ep["source_kind"]),
            ).fetchone()
            if not existing_endpoint:
                conn.execute(
                    """
                    INSERT INTO source_endpoints
                        (competitor_id, source_kind, purpose, endpoint_url, adapter_type,
                         trust_tier, poll_interval_seconds, enabled, is_primary, parser_config_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        comp_id,
                        ep["source_kind"],
                        ep["purpose"],
                        ep["endpoint_url"],
                        ep["adapter_type"],
                        ep.get("trust_tier", 1),
                        ep.get("poll_interval_seconds", 900),
                        ep.get("is_primary", 0),
                        json.dumps(ep.get("parser_config", {})),
                    ),
                )
            conn.execute(
                """
                UPDATE source_endpoints
                SET adapter_type = ?, trust_tier = ?, poll_interval_seconds = ?, enabled = 1,
                    is_primary = ?, parser_config_json = ?, updated_at = datetime('now')
                WHERE competitor_id = ? AND endpoint_url = ? AND purpose = ? AND source_kind = ?
                """,
                (
                    ep["adapter_type"],
                    ep.get("trust_tier", 1),
                    ep.get("poll_interval_seconds", 900),
                    ep.get("is_primary", 0),
                    json.dumps(ep.get("parser_config", {})),
                    comp_id,
                    ep["endpoint_url"],
                    ep["purpose"],
                    ep["source_kind"],
                ),
            )

    existing_endpoints = conn.execute(
        "SELECT id, competitor_id, endpoint_url, purpose, source_kind FROM source_endpoints"
    ).fetchall()
    for row in existing_endpoints:
        key = (row["competitor_id"], row["endpoint_url"], row["purpose"], row["source_kind"])
        if key not in seeded_endpoint_keys:
            conn.execute(
                "UPDATE source_endpoints SET enabled = 0, updated_at = datetime('now') WHERE id = ?",
                (row["id"],),
            )

    for query in build_discovery_queries():
        comp_id = slug_to_id.get(query["competitor_slug"]) if query["competitor_slug"] else None
        existing_query = conn.execute(
            """
            SELECT id FROM discovery_queries
            WHERE provider = ? AND query_family = ? AND endpoint_type = ? AND query_template = ?
              AND COALESCE(competitor_id, 0) = COALESCE(?, 0)
            """,
            (
                query["provider"],
                query["query_family"],
                query["endpoint_type"],
                query["query_template"],
                comp_id,
            ),
        ).fetchone()
        if not existing_query:
            conn.execute(
                """
                INSERT INTO discovery_queries
                    (competitor_id, provider, query_family, endpoint_type, query_template,
                     freshness_window, count, cadence_minutes, cooldown_minutes, priority,
                     trigger_only, enabled, max_monthly_calls, month_reset)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, datetime('now'))
                """,
                (
                    comp_id,
                    query["provider"],
                    query["query_family"],
                    query["endpoint_type"],
                    query["query_template"],
                    query["freshness_window"],
                    query["count"],
                    query["cadence_minutes"],
                    query["cooldown_minutes"],
                    query["priority"],
                    query.get("trigger_only", 0),
                    query["max_monthly_calls"],
                ),
            )
        conn.execute(
            """
            UPDATE discovery_queries
            SET freshness_window = ?, count = ?, cadence_minutes = ?, cooldown_minutes = ?,
                priority = ?, trigger_only = ?, enabled = 1, max_monthly_calls = ?
            WHERE provider = ? AND query_family = ? AND query_template = ?
              AND COALESCE(competitor_id, 0) = COALESCE(?, 0)
            """,
            (
                query["freshness_window"],
                query["count"],
                query["cadence_minutes"],
                query["cooldown_minutes"],
                query["priority"],
                query.get("trigger_only", 0),
                query["max_monthly_calls"],
                query["provider"],
                query["query_family"],
                query["query_template"],
                comp_id,
            ),
        )

    for comp_id in slug_to_id.values():
        conn.execute(
            """
            INSERT OR IGNORE INTO provider_status_current
                (competitor_id, overall_state, source_coverage, display_rank)
            VALUES (?, 'unknown', 'none', 3)
            """,
            (comp_id,),
        )

    conn.commit()
    logger.info("Aleph V2 DB ready with %s competitors", len(COMPETITORS))
