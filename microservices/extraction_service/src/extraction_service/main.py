"""
main.py — Extraction Service FastAPI Application
================================================
Endpoints:
  GET  /health                — service + model health check
  POST /v1/extract            — submit a document for extraction (async background job)
  GET  /v1/jobs/{job_id}      — poll job status / fetch results

The model is loaded ONCE at startup via the FastAPI lifespan.
All extraction jobs run in a background thread pool to avoid blocking the event loop.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import torch
import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from extraction_service.config import settings
from extraction_service.models import (
    ExtractionJobStatus,
    ExtractionRequest,
    ExtractionResult,
    HealthResponse,
)
from extraction_service.extractor import (
    load_model,
    is_model_loaded,
    extract_document,
)
from extraction_service.cropper import generate_crops_for_document

log = logging.getLogger(__name__)

# ── In-memory job store (sufficient for single-node; swap for Redis if needed) ─
_jobs: dict[str, ExtractionResult] = {}
_executor = ThreadPoolExecutor(max_workers=1)  # One extraction job at a time (GPU)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the Chandra OCR-2 model once at startup."""
    log.info("=== Extraction Service starting — loading model ===")
    try:
        load_model()
        log.info("=== Model ready ===")
    except Exception as exc:
        log.error(f"FATAL: Model failed to load — {exc}")
        # Allow the server to start even if model fails so /health can report it
    yield
    log.info("=== Extraction Service shutting down ===")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="NBE Extraction Service",
    description=(
        "Multimodal document extraction microservice. "
        "Accepts page images, runs Chandra OCR-2, generates visual crops. "
        "Reusable: any team with Arabic documents can use this service independently."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Background job runner ──────────────────────────────────────────────────────

def _run_extraction_job(job_id: str, request: ExtractionRequest) -> None:
    """
    Runs in a thread pool (not the async event loop).
    Updates _jobs[job_id] in place as stages complete.
    """
    _jobs[job_id].status = "running"
    output_dir = Path(settings.output_dir)

    try:
        meta = request.doc_meta
        log.info(f"[{job_id}] Starting extraction: {meta.doc_id} ({meta.total_pages} pages)")

        # Stage 1: OCR extraction
        pages, failed = extract_document(
            doc_id=meta.doc_id,
            doc_name=meta.doc_name,
            doc_type=meta.doc_type,
            language=meta.language,
            page_image_paths=request.page_image_paths,
            output_dir=output_dir,
        )

        # Stage 2: Crop generation
        # Derive the page image directory from the first page path
        if pages:
            page_image_dir = str(Path(request.page_image_paths[0]).parent)
            pages = generate_crops_for_document(pages, page_image_dir, output_dir)

            # Persist updated JSONs (with crop_path filled in)
            extractions_dir = output_dir / "extractions" / meta.doc_id
            for page in pages:
                out_path = extractions_dir / f"page_{page.page_num:03d}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(page.model_dump(), f, ensure_ascii=False, indent=2)

        _jobs[job_id].pages = pages
        _jobs[job_id].failed_pages = failed
        _jobs[job_id].output_dir = str(output_dir)
        _jobs[job_id].status = "complete"
        log.info(f"[{job_id}] Extraction complete: {len(pages)} pages, {len(failed)} failed")

        # Stage 3: Forward to indexing service (async fire-and-forget)
        if request.forward_to_indexing and settings.indexing_service_url:
            _forward_to_indexing(job_id, meta.doc_id, pages)

    except Exception as exc:
        log.error(f"[{job_id}] Job failed: {exc}", exc_info=True)
        _jobs[job_id].status = "failed"
        _jobs[job_id].error = str(exc)


def _forward_to_indexing(job_id: str, doc_id: str, pages: list) -> None:
    """POST extraction results to the indexing service."""
    url = f"{settings.indexing_service_url}/v1/index"
    payload = {
        "doc_id": doc_id,
        "pages": [p.model_dump() for p in pages],
        "source_job_id": job_id,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
        _jobs[job_id].forwarded_to_indexing = True
        log.info(f"[{job_id}] Forwarded to indexing service: {resp.json()}")
    except Exception as exc:
        log.warning(f"[{job_id}] Failed to forward to indexing service: {exc}")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    gpu_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if gpu_available else None
    vram_free = None
    if gpu_available:
        vram_free = round(torch.cuda.mem_get_info()[0] / 1e9, 2)

    return HealthResponse(
        status="ok" if is_model_loaded() else "degraded",
        model_loaded=is_model_loaded(),
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        vram_free_gb=vram_free,
    )


@app.post("/v1/extract", response_model=ExtractionJobStatus, status_code=202, tags=["Extraction"])
def submit_extraction(request: ExtractionRequest, background_tasks: BackgroundTasks) -> ExtractionJobStatus:
    """
    Submit a document for OCR extraction and crop generation.
    Returns immediately with a job_id; poll GET /v1/jobs/{job_id} for results.
    """
    if not is_model_loaded():
        raise HTTPException(status_code=503, detail="Model is not loaded yet. Try again shortly.")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = ExtractionResult(
        job_id=job_id,
        status="accepted",
        doc_id=request.doc_meta.doc_id,
    )

    background_tasks.add_task(_run_extraction_job, job_id, request)

    return ExtractionJobStatus(
        job_id=job_id,
        status="accepted",
        doc_id=request.doc_meta.doc_id,
        total_pages=request.doc_meta.total_pages,
        message="Extraction job accepted. Poll GET /v1/jobs/{job_id} for status.",
    )


@app.get("/v1/jobs/{job_id}", response_model=ExtractionResult, tags=["Extraction"])
def get_job_status(job_id: str) -> ExtractionResult:
    """Poll the status and results of an extraction job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return _jobs[job_id]


@app.get("/v1/jobs", tags=["Extraction"])
def list_jobs() -> dict:
    """List all known jobs and their statuses."""
    return {
        jid: {"status": j.status, "doc_id": j.doc_id}
        for jid, j in _jobs.items()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "extraction_service.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
