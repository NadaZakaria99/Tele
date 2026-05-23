"""
pipeline.py — Orchestration and status models for the ingestion pipeline.
"""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from datetime import datetime

class PipelineStatus(str, Enum):
    ACCEPTED = "accepted"
    FETCHING = "fetching"
    CONVERTING = "converting"
    EXTRACTING = "extracting"
    INDEXING = "indexing"
    COMPLETE = "complete"
    FAILED = "failed"

class OrchestratorJob(BaseModel):
    job_id: str
    doc_id: str
    doc_name: str
    status: PipelineStatus = PipelineStatus.ACCEPTED
    progress_pct: float = 0.0
    current_page: int = 0
    total_pages: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
