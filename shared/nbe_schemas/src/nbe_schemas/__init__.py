"""NBE shared Pydantic schemas — used by extraction_service, indexing_service, and rag_service."""

from nbe_schemas.documents import Block, PageResult, ChunkRecord, BlockType

__all__ = ["Block", "PageResult", "ChunkRecord", "BlockType"]
