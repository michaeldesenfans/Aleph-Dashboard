"""Repository for normalized evidence documents."""

from __future__ import annotations

import hashlib

from server.repositories.db import get_conn


def insert_document(doc: dict) -> int | None:
    conn = get_conn()
    content_hash = hashlib.sha256(
        f"{doc.get('title_raw', '')}|{doc.get('url', '')}".encode("utf-8")
    ).hexdigest()[:16]
    try:
        cur = conn.execute(
            """
            INSERT INTO documents
                (source_endpoint_id, discovery_query_id, external_id, url, canonical_url,
                 title_raw, snippet_raw, content_raw, content_clean, published_at,
                 content_hash, language, author, source_name, metadata_json, processing_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                doc.get("source_endpoint_id"),
                doc.get("discovery_query_id"),
                doc.get("external_id"),
                doc["url"],
                doc.get("canonical_url", doc["url"]),
                doc.get("title_raw"),
                doc.get("snippet_raw"),
                doc.get("content_raw"),
                doc.get("content_clean"),
                doc.get("published_at"),
                content_hash,
                doc.get("language", "en"),
                doc.get("author"),
                doc.get("source_name"),
                doc.get("metadata_json", "{}"),
            ),
        )
        conn.commit()
        doc_id = cur.lastrowid
        conn.close()
        return doc_id
    except Exception:
        conn.close()
        return None


def get_pending_documents(limit: int = 50):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT d.*, se.endpoint_url, c.slug AS competitor_slug, c.name AS competitor_name
        FROM documents d
        LEFT JOIN source_endpoints se ON se.id = d.source_endpoint_id
        LEFT JOIN discovery_queries dq ON dq.id = d.discovery_query_id
        LEFT JOIN competitors c ON c.id = COALESCE(se.competitor_id, dq.competitor_id)
        WHERE d.processing_status = 'pending'
        ORDER BY COALESCE(d.published_at, d.fetched_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_document_status(doc_id: int, status: str, rejection_reason: str | None = None):
    conn = get_conn()
    conn.execute(
        """
        UPDATE documents
        SET processing_status = ?, rejection_reason = ?
        WHERE id = ?
        """,
        (status, rejection_reason, doc_id),
    )
    conn.commit()
    conn.close()


def url_exists(url: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM documents WHERE url = ?", (url,)).fetchone()
    conn.close()
    return row is not None


def get_recent_documents(hours: int = 168, limit: int = 50):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT *
        FROM documents
        WHERE fetched_at >= datetime('now', ?)
        ORDER BY fetched_at DESC
        LIMIT ?
        """,
        (f"-{hours} hours", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
