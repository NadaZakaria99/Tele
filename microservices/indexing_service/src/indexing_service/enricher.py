"""
enricher.py — Chunk Enrichment & Noise Filtration
==================================================
Migrated and improved from my_work/build_catalog.py.

Key transformations:
  1. Rolling header propagation  — prepends last-seen section header to text/list blocks
  2. Noise filtration            — drops footers, page numbers, stub blocks (< 3 words)
  3. Table handling              — uses HTML table_data for embedding instead of raw text dump
  4. Cross-page header memory   — header context persists across pages within a document

Returns LangChain Document objects ready for the embedding pipeline.
"""

from __future__ import annotations

import json
import logging
from langchain_core.documents import Document

from nbe_schemas.documents import BlockType, PageResult
from indexing_service.config import settings

log = logging.getLogger(__name__)

# Arabic pagination artifact keywords — headers containing these are NOT used
# as rolling headers (they are page number / boilerplate blocks)
_PAGINATION_KEYWORDS = ("صفحة", "صفحه", "page", "البنك المركزي")

# Minimum word count for a text/list block to be considered non-noise
_MIN_WORD_COUNT = 3


def enrich_pages(
    pages: list[PageResult],
    doc_type: str,
    ingest_timestamp: str,
) -> tuple[list[Document], int]:
    """
    Convert a list of PageResult objects into enriched LangChain Documents.

    The rolling header persists across pages within a document.

    Args:
        pages:            Ordered list of PageResult objects for one document.
        doc_type:         e.g. "SOP" or "Legal Circular"
        ingest_timestamp: ISO 8601 timestamp string

    Returns:
        (documents, filtered_count)
        - documents:      List of LangChain Document objects ready for embedding.
        - filtered_count: Number of blocks dropped as noise.
    """
    documents: list[Document] = []
    filtered_count = 0
    current_header = ""  # Persists across pages

    for page in sorted(pages, key=lambda p: p.page_num):
        for block in page.blocks:
            raw_text = block.text.strip() if block.text else ""

            # ── 1. Update rolling header ───────────────────────────────────────
            if block.block_type == BlockType.HEADER:
                if raw_text and not any(kw in raw_text for kw in _PAGINATION_KEYWORDS):
                    current_header = raw_text
                # Headers are indexed as standalone chunks too (not skipped)

            # ── 2. Filtration ──────────────────────────────────────────────────
            if block.block_type == BlockType.FOOTER:
                filtered_count += 1
                continue

            # Drop short text/list blocks (noise, stray OCR artifacts)
            if block.block_type not in (BlockType.TABLE, BlockType.HEADER, BlockType.FIGURE):
                if not raw_text or len(raw_text.split()) < _MIN_WORD_COUNT:
                    filtered_count += 1
                    continue

            # ── 3. Enrichment ──────────────────────────────────────────────────
            # Determine the text that will be embedded
            if block.block_type == BlockType.TABLE and block.table_data:
                # Use the structured HTML for tables — the LLM can parse it better
                embed_text = block.table_data
                if current_header:
                    embed_text = f"[{current_header}]\n{embed_text}"
            elif block.block_type in (BlockType.TEXT, BlockType.LIST) and current_header:
                embed_text = f"[{current_header}] {raw_text}"
            else:
                embed_text = raw_text

            # ── 4. Build LangChain Document ────────────────────────────────────
            metadata = {
                "chunk_id": block.block_id,
                "doc_id": page.doc_id,
                "doc_name": page.doc_name,
                "doc_type": doc_type,
                "page_num": page.page_num,
                "block_id": block.block_id,
                "block_type": block.block_type.value,
                "raw_text": raw_text,
                "language": block.language,
                "bbox": json.dumps(block.bbox.as_list()) if block.bbox else None,
                "crop_path": block.crop_path,
                "crop_minio_url": "",   # filled by object_store.py after upload
                "page_image_minio_url": "",  # filled by object_store.py
                "ingest_timestamp": ingest_timestamp,
            }

            documents.append(
                Document(page_content=embed_text, metadata=metadata)
            )

    return documents, filtered_count
