"""
pipeline.py — LangChain Indexing Pipeline
==========================================
Orchestrates the full ingestion flow:
  1. Enrich: header propagation + noise filter → LangChain Documents
  2. Split: RecursiveCharacterTextSplitter for long text blocks (tables kept whole)
  3. Upload: crops + page images → MinIO (fills minio URL metadata fields)
  4. Embed + Upsert: NVIDIAEmbeddings → Milvus via LangChain Milvus vectorstore
  5. Register: catalog entry in SQLite

Also handles the LEGACY path: reading existing my_work/pipeline_output/ JSONs
directly without going through the extraction service first.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from nbe_schemas.documents import BlockType, PageResult
from indexing_service.config import settings
from indexing_service.enricher import enrich_pages
from indexing_service.vectorstore import get_embeddings, get_vectorstore, drop_doc_vectors
from indexing_service.object_store import upload_crops, upload_page_images
from indexing_service.catalog import register_ingest, is_indexed

log = logging.getLogger(__name__)

# Text splitter — applied to text/list/header blocks only.
# Tables and figures are kept as single chunks.
_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    length_function=len,
    separators=["\n\n", "\n", "。", "،", " ", ""],
)


def _split_documents(documents: list[Document]) -> list[Document]:
    """Split long text blocks; keep tables and figures as single chunks."""
    result: list[Document] = []
    for doc in documents:
        block_type = doc.metadata.get("block_type", "text")
        if block_type in (BlockType.TABLE.value, BlockType.FIGURE.value):
            # Never split tables or figures
            result.append(doc)
        else:
            splits = _text_splitter.split_documents([doc])
            # Preserve chunk suffix on chunk_id for traceability
            for i, split in enumerate(splits):
                if i > 0:
                    split.metadata["chunk_id"] = f"{doc.metadata['chunk_id']}_c{i}"
            result.extend(splits)
    return result


def _apply_minio_urls(
    documents: list[Document],
    crop_url_map: dict[str, str],
    page_url_map: dict[str, str],
    doc_id: str,
) -> list[Document]:
    """Fill in crop_minio_url and page_image_minio_url metadata fields."""
    for doc in documents:
        crop_path = doc.metadata.get("crop_path") or ""
        # The crop_path in the JSON is relative from pipeline_output (e.g. crops/rtgs/page_001/...)
        if crop_path and crop_path in crop_url_map:
            doc.metadata["crop_minio_url"] = crop_url_map[crop_path]

        page_num = doc.metadata.get("page_num")
        page_filename = f"page_{page_num:03d}.png" if page_num else ""
        if page_filename and page_filename in page_url_map:
            doc.metadata["page_image_minio_url"] = page_url_map[page_filename]

    return documents


def run_indexing_pipeline(
    pages: list[PageResult],
    doc_id: str,
    doc_name: str,
    doc_type: str,
    pipeline_output_dir: Path,
    docs_images_dir: Path | None,
    source_job_id: str | None = None,
) -> dict:
    """
    Full indexing pipeline for one document.

    Args:
        pages:                Ordered list of PageResult objects.
        doc_id:               Document identifier.
        doc_name:             Original filename.
        doc_type:             "SOP" | "Legal Circular" | ...
        pipeline_output_dir:  Root of the output directory (for crops).
        docs_images_dir:      Directory of page PNGs (for MinIO upload). None = skip page upload.
        source_job_id:        Traceability link to the extraction job.

    Returns:
        Summary dict with counts.
    """
    ingest_ts = datetime.now(timezone.utc).isoformat()

    # ── Handle re-ingestion policy ────────────────────────────────────────────
    if settings.reingestion_policy == "replace":
        drop_doc_vectors(doc_id)
    elif settings.reingestion_policy == "skip" and is_indexed(doc_id):
        log.info(f"Skipping '{doc_id}' — already indexed (policy=skip)")
        return {"status": "skipped", "doc_id": doc_id}

    # ── Step 1: Enrich ────────────────────────────────────────────────────────
    log.info(f"[{doc_id}] Step 1/4: Enriching {len(pages)} pages...")
    documents, filtered_count = enrich_pages(pages, doc_type, ingest_ts)
    log.info(f"[{doc_id}] {len(documents)} chunks after enrichment, {filtered_count} filtered")

    # ── Step 2: Split text blocks ──────────────────────────────────────────────
    log.info(f"[{doc_id}] Step 2/4: Splitting long text blocks...")
    documents = _split_documents(documents)
    log.info(f"[{doc_id}] {len(documents)} chunks after splitting")

    # ── Step 3: Upload to MinIO + fill URL metadata ────────────────────────────
    log.info(f"[{doc_id}] Step 3/4: Uploading to MinIO...")
    crop_url_map = upload_crops(pipeline_output_dir, doc_id)
    page_url_map = {}
    if docs_images_dir:
        page_url_map = upload_page_images(docs_images_dir, doc_id)

    documents = _apply_minio_urls(documents, crop_url_map, page_url_map, doc_id)
    minio_uploads = len(crop_url_map) + len(page_url_map)

    # ── Step 4: Embed + Upsert into Milvus ───────────────────────────────────
    log.info(f"[{doc_id}] Step 4/4: Embedding and indexing {len(documents)} chunks...")
    embeddings = get_embeddings()
    vectorstore = get_vectorstore(embeddings)

    # Use chunk_id as the document ID in Milvus for deterministic upserts
    ids = [doc.metadata["chunk_id"] for doc in documents]
    vectorstore.add_documents(documents, ids=ids)
    log.info(f"[{doc_id}] Indexed {len(documents)} vectors into Milvus")

    # ── Step 5: Register in catalog ────────────────────────────────────────────
    register_ingest(
        doc_id=doc_id,
        doc_name=doc_name,
        doc_type=doc_type,
        total_pages=len(pages),
        total_chunks=len(documents),
        chunks_filtered=filtered_count,
        source_job_id=source_job_id,
        status="complete",
    )

    return {
        "status": "complete",
        "doc_id": doc_id,
        "chunks_indexed": len(documents),
        "chunks_filtered": filtered_count,
        "minio_uploads": minio_uploads,
    }


# ── Legacy import path ─────────────────────────────────────────────────────────

def run_legacy_indexing(
    extractions_dir: Path,
    doc_id: str | None,
    pipeline_output_dir: Path,
    docs_images_dir: Path | None = None,
) -> list[dict]:
    """
    Index from existing my_work/pipeline_output/extractions/ directory.
    This is Milestone 2: consuming the data that already exists.

    Args:
        extractions_dir:      Path to the extractions directory.
        doc_id:               If None, process all doc subdirectories found.
        pipeline_output_dir:  Root output dir for MinIO crop uploads.
        docs_images_dir:      Page image directory. None = skip page image upload.

    Returns:
        List of result dicts, one per document processed.
    """
    results = []

    if doc_id:
        doc_dirs = [extractions_dir / doc_id]
    else:
        doc_dirs = [d for d in extractions_dir.iterdir() if d.is_dir()]

    for doc_dir in sorted(doc_dirs):
        current_doc_id = doc_dir.name
        log.info(f"Legacy indexing: processing '{current_doc_id}'...")

        json_files = sorted(doc_dir.glob("page_*.json"))
        if not json_files:
            log.warning(f"No JSON files found in {doc_dir}")
            continue

        pages: list[PageResult] = []
        for jf in json_files:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)
            pages.append(PageResult.model_validate(data))

        if not pages:
            continue

        # Derive doc_name and doc_type from first page
        first = pages[0]
        result = run_indexing_pipeline(
            pages=pages,
            doc_id=current_doc_id,
            doc_name=first.doc_name,
            doc_type=first.doc_type,
            pipeline_output_dir=pipeline_output_dir,
            docs_images_dir=docs_images_dir,
            source_job_id="legacy_import",
        )
        results.append(result)

    return results
