"""
models.py — RAG Service API Schemas
"""

from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    role: str = "teller"


class SourceChunk(BaseModel):
    id: int
    doc_id: str
    page_num: int
    content: str
    crop_url: Optional[str] = None
    page_image_url: Optional[str] = None
    block_type: str = "text"
    cosine_distance: Optional[float] = None
    reranker_score: Optional[float] = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceChunk] = []
    blocked: bool = False
    latency_ms: int = 0


class HealthResponse(BaseModel):
    status: str
    milvus: str
    collection_entities: int = 0
