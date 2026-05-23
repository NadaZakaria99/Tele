"""
models.py — Indexing Service API Schemas
========================================
"""

from pydantic import BaseModel, Field
from nbe_schemas.documents import PageResult


class IndexRequest(BaseModel):
    """POST /v1/index — submit pages for indexing."""

    doc_id: str
    pages: list[PageResult]
    source_job_id: str | None = Field(
        default=None,
        description="Job ID from extraction_service for traceability",
    )


class LegacyIndexRequest(BaseModel):
    """
    POST /v1/index/legacy — ingest data from the existing my_work/pipeline_output/
    directory without going through the extraction service.
    This is the 'consume existing data' path for the first milestone.
    """

    doc_id: str | None = Field(
        default=None,
        description="If None, all docs found in extractions_dir are indexed",
    )
    extractions_dir: str = Field(
        default="/data/legacy/pipeline_output/extractions",
        description="Absolute path (inside container) to the existing extractions folder",
    )
    pipeline_output_dir: str | None = Field(
        default=None,
        description="Root of the output directory (where 'crops' folder is). If None, uses settings.",
    )


class IndexJobStatus(BaseModel):
    """Returned immediately upon accepting an indexing request."""

    job_id: str
    status: str  # "accepted" | "running" | "complete" | "failed"
    doc_id: str
    message: str = ""


class IndexJobResult(BaseModel):
    """Full result returned when polling GET /v1/jobs/{job_id}."""

    job_id: str
    status: str
    doc_id: str
    chunks_indexed: int = 0
    chunks_filtered: int = 0
    minio_uploads: int = 0
    catalog_registered: bool = False
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    milvus: str
    minio: str
    catalog: str
    collection_entities: int = 0
