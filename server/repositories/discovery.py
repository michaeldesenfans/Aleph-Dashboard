"""Repository for discovery queries, run logs, and Brave budget management."""

from __future__ import annotations

import json

from server.repositories.db import get_conn


def get_due_queries(limit: int = 10):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT dq.*, c.slug AS competitor_slug, c.name AS competitor_name, c.metadata_json
        FROM discovery_queries dq
        LEFT JOIN competitors c ON c.id = dq.competitor_id
        WHERE dq.enabled = 1
          AND dq.trigger_only = 0
          AND (dq.max_monthly_calls IS NULL OR dq.calls_this_month < dq.max_monthly_calls)
          AND (
                dq.last_run_at IS NULL
                OR datetime(dq.last_run_at, printf('+%d minutes', dq.cooldown_minutes)) <= datetime('now')
              )
        ORDER BY dq.priority ASC, dq.cadence_minutes ASC, dq.id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_query_run(query_id: int, result_count: int = 0):
    conn = get_conn()
    conn.execute(
        """
        UPDATE discovery_queries
        SET calls_this_month = calls_this_month + 1,
            last_run_at = datetime('now'),
            last_result_count = ?
        WHERE id = ?
        """,
        (result_count, query_id),
    )
    conn.commit()
    conn.close()


def reset_monthly_counters():
    conn = get_conn()
    conn.execute(
        "UPDATE discovery_queries SET calls_this_month = 0, month_reset = datetime('now')"
    )
    conn.commit()
    conn.close()


def get_budget_snapshot():
    conn = get_conn()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(calls_this_month), 0) AS total_calls,
               COALESCE(SUM(max_monthly_calls), 0) AS max_calls
        FROM discovery_queries
        WHERE enabled = 1
        """
    ).fetchone()
    conn.close()
    return dict(row)


def log_run(run_type: str, trigger_type: str = "scheduled") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO discovery_runs (run_type, trigger_type) VALUES (?, ?)",
        (run_type, trigger_type),
    )
    conn.commit()
    run_id = cur.lastrowid
    conn.close()
    return run_id


def finish_run(run_id: int, status: str, stats: dict | None = None, error: str | None = None):
    conn = get_conn()
    conn.execute(
        """
        UPDATE discovery_runs
        SET status = ?, finished_at = datetime('now'), stats_json = ?, error_summary = ?
        WHERE id = ?
        """,
        (status, json.dumps(stats or {}), error, run_id),
    )
    conn.commit()
    conn.close()


def get_recent_runs(limit: int = 10):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM discovery_runs ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
