"""
vectorstore.py — LangChain Milvus Vector Store Setup
=====================================================
Creates and manages the Milvus collection used by both the indexing service
(writes) and the rag_service (reads).
"""

from __future__ import annotations

import logging
from langchain_milvus import Milvus
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

from indexing_service.config import settings

log = logging.getLogger(__name__)

# Milvus field names — must match the rag_service retriever config
VECTOR_FIELD = "embedding"
TEXT_FIELD = "text"    # LangChain Milvus uses this for page_content


def get_embeddings() -> NVIDIAEmbeddings:
    """Return a configured NVIDIAEmbeddings instance pointing at the local NIM."""
    return NVIDIAEmbeddings(
        model=settings.embedding_model,
        base_url=settings.inference_base_url,
        api_key=settings.nvidia_api_key,
        truncate="END",
    )


def get_vectorstore(embeddings: NVIDIAEmbeddings | None = None) -> Milvus:
    """
    Return a LangChain Milvus client connected to the configured collection.
    Used for both upsert (indexing) and search (RAG query via rag_service).
    """
    if embeddings is None:
        embeddings = get_embeddings()

    return Milvus(
        embedding_function=embeddings,
        collection_name=settings.milvus_collection,
        connection_args={
            "uri": f"http://{settings.milvus_host}:{settings.milvus_port}",
        },
        vector_field=VECTOR_FIELD,
        text_field=TEXT_FIELD,
        auto_id=False,
        drop_old=False,   # Never drop silently; controlled explicitly
    )


def drop_doc_vectors(doc_id: str) -> int:
    """
    Delete all Milvus vectors for a given doc_id (re-ingestion replace policy).
    Returns the number of entities deleted.
    """
    from pymilvus import connections, Collection, utility, MilvusException
    connections.connect(
        "default",
        host=settings.milvus_host,
        port=settings.milvus_port,
    )

    if not utility.has_collection(settings.milvus_collection):
        log.info(f"Collection '{settings.milvus_collection}' does not exist yet — nothing to drop.")
        return 0

    col = Collection(settings.milvus_collection)
    try:
        col.load()
    except MilvusException as e:
        if "index not found" in str(e):
            # Collection exists but has no index — it's an empty/broken state from a
            # previous failed run. Drop it so it gets recreated cleanly.
            log.warning(f"Collection '{settings.milvus_collection}' has no index; dropping for clean recreation.")
            utility.drop_collection(settings.milvus_collection)
            return 0
        raise

    expr = f'doc_id == "{doc_id}"'
    result = col.delete(expr)
    count = result.delete_count
    log.info(f"Dropped {count} vectors for doc_id='{doc_id}'")
    return count


def collection_entity_count() -> int:
    """Return the total number of entities in the collection."""
    from pymilvus import connections, Collection, utility
    connections.connect("default", host=settings.milvus_host, port=settings.milvus_port)
    if not utility.has_collection(settings.milvus_collection):
        return 0
    col = Collection(settings.milvus_collection)
    col.load()
    return col.num_entities
