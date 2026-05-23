"""
main.py — Indexing Service FastAPI Application
===============================================
Endpoints:
  GET  /health                        — health check (Milvus, MinIO, catalog)
  POST /v1/index                      — index pages from extraction_service output
  POST /v1/index/legacy               — index from existing pipeline_output directory
  GET  /v1/jobs/{job_id}              — poll job status
  GET  /v1/catalog                    — list all indexed documents
  GET  /v1/catalog/{doc_id}           — get catalog entry for a document
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from indexing_service.config import settings
from indexing_service.models import (
    HealthResponse,
    IndexJobResult,
    IndexJobStatus,
    IndexRequest,
    LegacyIndexRequest,
)
from indexing_service.pipeline import run_indexing_pipeline, run_legacy_indexing
from indexing_service.vectorstore import collection_entity_count
from indexing_service.object_store import health_check as minio_health
from indexing_service.catalog import health_check as catalog_health, list_entries, get_entry

log = logging.getLogger(__name__)

# ── In-memory job store ────────────────────────────────────────────────────────
_jobs: dict[str, IndexJobResult] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== Indexing Service starting ===")
    yield
    log.info("=== Indexing Service shutting down ===")


app = FastAPI(
    title="NBE Indexing Service",
    description=(
        "Document indexing microservice. Consumes extraction output, embeds chunks "
        "via local NIM, indexes into Milvus, uploads assets to MinIO, and registers "
        "provenance in a SQLite catalog. Reusable for any structured document corpus."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ── Background runners ─────────────────────────────────────────────────────────

def _run_index_job(job_id: str, request: IndexRequest) -> None:
    _jobs[job_id].status = "running"
    try:
        result = run_indexing_pipeline(
            pages=request.pages,
            doc_id=request.doc_id,
            doc_name=request.pages[0].doc_name if request.pages else request.doc_id,
            doc_type=request.pages[0].doc_type if request.pages else "Unknown",
            pipeline_output_dir=Path(settings.pipeline_output_dir),
            docs_images_dir=Path(settings.data_dir) / "docs_images",
            source_job_id=request.source_job_id,
        )
        _jobs[job_id].status = result.get("status", "complete")
        _jobs[job_id].chunks_indexed = result.get("chunks_indexed", 0)
        _jobs[job_id].chunks_filtered = result.get("chunks_filtered", 0)
        _jobs[job_id].minio_uploads = result.get("minio_uploads", 0)
        _jobs[job_id].catalog_registered = True
    except Exception as exc:
        log.error(f"[{job_id}] Indexing job failed: {exc}", exc_info=True)
        _jobs[job_id].status = "failed"
        _jobs[job_id].error = str(exc)


def _run_legacy_job(job_id: str, request: LegacyIndexRequest) -> None:
    _jobs[job_id].status = "running"
    try:
        results = run_legacy_indexing(
            extractions_dir=Path(request.extractions_dir),
            doc_id=request.doc_id,
            pipeline_output_dir=Path(request.pipeline_output_dir) if request.pipeline_output_dir else Path(settings.pipeline_output_dir),
            docs_images_dir=Path(settings.data_dir) / "docs_images",
        )
        total_chunks = sum(r.get("chunks_indexed", 0) for r in results)
        total_filtered = sum(r.get("chunks_filtered", 0) for r in results)
        _jobs[job_id].status = "complete"
        _jobs[job_id].chunks_indexed = total_chunks
        _jobs[job_id].chunks_filtered = total_filtered
        _jobs[job_id].catalog_registered = True
    except Exception as exc:
        log.error(f"[{job_id}] Legacy indexing failed: {exc}", exc_info=True)
        _jobs[job_id].status = "failed"
        _jobs[job_id].error = str(exc)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    try:
        entities = collection_entity_count()
        milvus_status = "connected"
    except Exception as e:
        entities = 0
        milvus_status = f"error: {e}"

    return HealthResponse(
        status="ok",
        milvus=milvus_status,
        minio="ok" if minio_health() else "error",
        catalog="ok" if catalog_health() else "error",
        collection_entities=entities,
    )


@app.post("/v1/index", response_model=IndexJobStatus, status_code=202, tags=["Indexing"])
def index_pages(request: IndexRequest, background_tasks: BackgroundTasks) -> IndexJobStatus:
    """
    Index document pages received from the extraction service.
    Accepts a list of PageResult objects and runs the full indexing pipeline asynchronously.
    """
    if not request.pages:
        raise HTTPException(status_code=400, detail="No pages provided.")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = IndexJobResult(
        job_id=job_id, status="accepted", doc_id=request.doc_id
    )
    background_tasks.add_task(_run_index_job, job_id, request)

    return IndexJobStatus(
        job_id=job_id,
        status="accepted",
        doc_id=request.doc_id,
        message=f"Indexing {len(request.pages)} pages. Poll GET /v1/jobs/{job_id}",
    )


@app.post("/v1/index/legacy", response_model=IndexJobStatus, status_code=202, tags=["Indexing"])
def index_legacy(request: LegacyIndexRequest, background_tasks: BackgroundTasks) -> IndexJobStatus:
    """
    Index from an existing pipeline_output/extractions/ directory.
    Use this for Milestone 2: consuming data from the original my_work/ prototype.
    """
    job_id = str(uuid.uuid4())
    doc_label = request.doc_id or "all"
    _jobs[job_id] = IndexJobResult(
        job_id=job_id, status="accepted", doc_id=doc_label
    )
    background_tasks.add_task(_run_legacy_job, job_id, request)

    return IndexJobStatus(
        job_id=job_id,
        status="accepted",
        doc_id=doc_label,
        message=f"Legacy indexing started. Poll GET /v1/jobs/{job_id}",
    )


@app.get("/v1/jobs/{job_id}", response_model=IndexJobResult, tags=["Indexing"])
def get_job(job_id: str) -> IndexJobResult:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return _jobs[job_id]


@app.get("/v1/catalog", tags=["Catalog"])
def list_catalog() -> list[dict]:
    """List all documents registered in the catalog."""
    return list_entries()


@app.get("/v1/catalog/{doc_id}", tags=["Catalog"])
def get_catalog_entry(doc_id: str) -> dict:
    entry = get_entry(doc_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not in catalog.")
    return entry


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "indexing_service.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
