"""Repository helpers for competitors and seeded source endpoints."""

from __future__ import annotations

from server.repositories.db import get_conn


def get_all_competitors(active_only: bool = True, pinned_only: bool = False):
    conn = get_conn()
    clauses = []
    params: list = []
    if active_only:
        clauses.append("active = 1")
    if pinned_only:
        clauses.append("is_pinned = 1")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM competitors{where} ORDER BY display_order, name",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pinned_competitors():
    return get_all_competitors(active_only=True, pinned_only=True)


def get_competitor_by_slug(slug: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM competitors WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_competitor_id_map():
    conn = get_conn()
    rows = conn.execute("SELECT id, slug FROM competitors WHERE active = 1").fetchall()
    conn.close()
    return {r["slug"]: r["id"] for r in rows}


def get_source_endpoints(
    *,
    purpose: str | None = None,
    enabled_only: bool = True,
    pinned_only: bool = False,
):
    conn = get_conn()
    clauses = []
    params: list = []
    if enabled_only:
        clauses.append("se.enabled = 1")
    if purpose:
        clauses.append("se.purpose = ?")
        params.append(purpose)
    if pinned_only:
        clauses.append("c.is_pinned = 1")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT se.*, c.slug AS competitor_slug, c.name AS competitor_name, c.display_order, c.metadata_json
        FROM source_endpoints se
        JOIN competitors c ON c.id = se.competitor_id
        {where}
        ORDER BY c.display_order, se.is_primary DESC, se.trust_tier, se.poll_interval_seconds
        """,
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_endpoint_check(endpoint_id: int, success: bool, error_msg: str | None = None):
    conn = get_conn()
    if success:
        conn.execute(
            """
            UPDATE source_endpoints
            SET last_checked_at = datetime('now'),
                last_success_at = datetime('now'),
                last_error_msg = NULL,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (endpoint_id,),
        )
    else:
        conn.execute(
            """
            UPDATE source_endpoints
            SET last_checked_at = datetime('now'),
                last_error_at = datetime('now'),
                last_error_msg = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (error_msg, endpoint_id),
        )
    conn.commit()
    conn.close()
