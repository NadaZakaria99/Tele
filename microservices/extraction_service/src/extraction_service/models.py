"""
models.py — Extraction Service API Schemas
==========================================
Pydantic models for the REST API layer (request/response).
The core data models (Block, PageResult) live in nbe_schemas.
"""

from pydantic import BaseModel, Field
from nbe_schemas.documents import PageResult


# ── Request models ─────────────────────────────────────────────────────────────

class DocMeta(BaseModel):
    """Metadata the caller supplies about the document being extracted."""

    doc_id: str = Field(description="Short identifier, e.g. 'rtgs', 'legal_circular_1'")
    doc_name: str = Field(description="Original filename, e.g. 'rtgs_procedures.pdf'")
    doc_type: str = Field(default="SOP", description="Document category")
    language: str = Field(default="ar")
    total_pages: int = Field(ge=1)


class ExtractionRequest(BaseModel):
    """POST /v1/extract — submit a document for OCR extraction."""

    doc_meta: DocMeta
    # Paths to the page PNG images on the shared volume (mounted at /data)
    page_image_paths: list[str] = Field(
        description="Ordered list of absolute paths (inside the container) to page PNG files"
    )
    # If True, the extraction service will POST results to the indexing service
    # automatically when done. Overrides the global config for this request.
    forward_to_indexing: bool = True


# ── Response models ────────────────────────────────────────────────────────────

class ExtractionJobStatus(BaseModel):
    """Returned immediately upon accepting an extraction request."""

    job_id: str
    status: str  # "accepted" | "running" | "complete" | "failed"
    doc_id: str
    total_pages: int
    message: str = ""


class ExtractionResult(BaseModel):
    """Full result returned when a job is complete (GET /v1/jobs/{job_id})."""

    job_id: str
    status: str
    doc_id: str
    pages: list[PageResult] = []
    failed_pages: list[dict] = []
    output_dir: str = ""
    forwarded_to_indexing: bool = False
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    gpu_available: bool
    gpu_name: str | None = None
    vram_free_gb: float | None = None
