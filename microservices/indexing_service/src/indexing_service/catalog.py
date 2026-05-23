"""
catalog.py — SQLite Document Catalog
=====================================
Tracks ingested documents for provenance, de-duplication, and audit.
The catalog is the authoritative record of what is indexed in Milvus.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from indexing_service.config import settings

log = logging.getLogger(__name__)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS catalog_entries (
    doc_id              TEXT PRIMARY KEY,
    doc_name            TEXT,
    doc_type            TEXT,
    file_hash           TEXT,
    total_pages         INTEGER,
    total_chunks        INTEGER,
    chunks_filtered     INTEGER,
    ingest_status       TEXT DEFAULT 'pending',
    ingest_timestamp    TEXT,
    milvus_collection   TEXT,
    minio_crops_bucket  TEXT,
    minio_pages_bucket  TEXT,
    source_job_id       TEXT
);
"""


def _connect() -> sqlite3.Connection:
    db_path = Path(settings.catalog_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_SQL)
    conn.commit()
    return conn


def register_ingest(
    doc_id: str,
    doc_name: str,
    doc_type: str,
    total_pages: int,
    total_chunks: int,
    chunks_filtered: int,
    source_job_id: str | None = None,
    file_hash: str | None = None,
    status: str = "complete",
) -> None:
    """Insert or replace a catalog entry for a successfully indexed document."""
    conn = _connect()
    conn.execute(
        """
        INSERT OR REPLACE INTO catalog_entries
            (doc_id, doc_name, doc_type, file_hash, total_pages, total_chunks,
             chunks_filtered, ingest_status, ingest_timestamp,
             milvus_collection, minio_crops_bucket, minio_pages_bucket, source_job_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id, doc_name, doc_type, file_hash, total_pages, total_chunks,
            chunks_filtered, status,
            datetime.now(timezone.utc).isoformat(),
            settings.milvus_collection,
            settings.minio_bucket_crops,
            settings.minio_bucket_pages,
            source_job_id,
        ),
    )
    conn.commit()
    conn.close()
    log.info(f"Catalog: registered '{doc_id}' ({total_chunks} chunks, status={status})")


def get_entry(doc_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM catalog_entries WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_entries() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM catalog_entries ORDER BY ingest_timestamp DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_indexed(doc_id: str) -> bool:
    entry = get_entry(doc_id)
    return entry is not None and entry.get("ingest_status") == "complete"


def sha256_file(file_path: str) -> str:
    """Compute SHA-256 hash of a file for de-duplication."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def health_check() -> bool:
    try:
        _connect()
        return True
    except Exception:
        return False
