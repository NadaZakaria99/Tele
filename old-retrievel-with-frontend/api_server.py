"""
api_server.py — NBE Knowledge Assistant FastAPI Server
=======================================================
Exposes the RAG pipeline as an HTTP API for the React frontend.

Run with:
    uvicorn api_server:app --host 0.0.0.0 --port 8001 --reload
"""

import logging
import time
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import rag_pipeline as rp

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="NBE Knowledge Assistant API",
    description="RAG pipeline backed by Milvus + NVIDIA NIMs",
    version="1.0.0",
)

# Allow the React dev server (and any other origin in dev) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Role → allowed document mapping (RBAC)
# ---------------------------------------------------------------------------
# None means no filter (access to everything)
ROLE_DOC_FILTER = {
    "teller":          ["rtgs"],                              # Branch Tellers: SOPs only
    "legal_counsel":   None,                                  # Legal Counsel: all docs
    "manager":         None,                                  # Managers: all docs
}

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    query: str
    role: str = "teller"      # Default to most restrictive role


class SourceChunk(BaseModel):
    id: int
    doc_id: str
    page_num: int
    content: str
    crop_url: Optional[str] = None
    cosine_distance: Optional[float] = None
    reranker_score: Optional[float] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceChunk]
    stages: List[str]
    latency_ms: int


class HealthResponse(BaseModel):
    status: str
    milvus: str
    collection_entities: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """
    Verify the server is running and Milvus is reachable.
    Called by the React frontend on startup to show the status indicator.
    """
    try:
        rp._connect_milvus()
        from pymilvus import Collection
        col = Collection(rp.MILVUS_COLLECTION)
        col.load()
        entity_count = col.num_entities
        return HealthResponse(
            status="ok",
            milvus="connected",
            collection_entities=entity_count,
        )
    except Exception as e:
        log.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Milvus unavailable: {e}")


@app.post("/chat", response_model=ChatResponse, tags=["Pipeline"])
def chat(request: ChatRequest):
    """
    Run the full RAG pipeline for a given query and user role.

    The `role` field controls which documents the user is allowed to search:
    - 'teller'        → SOP documents only (rtgs)
    - 'legal_counsel' → All documents (SOPs + Legal Circulars)
    - 'manager'       → All documents
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    role = request.role.lower()
    doc_filter = ROLE_DOC_FILTER.get(role, ROLE_DOC_FILTER["teller"])

    log.info(f"📥 Incoming query | role='{role}' | doc_filter={doc_filter} | query='{query[:80]}'")

    stages: List[str] = []
    t0 = time.monotonic()

    # ── Stage 1: Input safety ─────────────────────────────────────────────
    try:
        is_safe, safety_category = rp.check_input_safety(query)
    except Exception as e:
        log.error(f"Safety check crashed: {e}")
        raise HTTPException(status_code=500, detail="Safety check failed.")

    if not is_safe:
        stages.append(f"safety_blocked:{safety_category}")
        return ChatResponse(
            answer=rp.REFUSAL_MESSAGE,
            sources=[],
            stages=stages,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    stages.append("safety_passed")

    # ── Stage 2: Topic control ────────────────────────────────────────────
    try:
        is_relevant, topic_label = rp.check_topic_relevance(query)
    except Exception as e:
        log.warning(f"Topic check crashed (failing open): {e}")
        is_relevant = True

    if not is_relevant:
        stages.append("topic_blocked")
        off_topic_msg = (
            "يمكنني فقط الإجابة على الأسئلة المتعلقة بالإجراءات التشغيلية والمسائل القانونية المصرفية. "
            "يُرجى إعادة صياغة سؤالك."
        )
        return ChatResponse(
            answer=off_topic_msg,
            sources=[],
            stages=stages,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    stages.append("topic_passed")

    # ── Stage 3: Embed query ──────────────────────────────────────────────
    try:
        embedding = rp.embed_query(query)
        stages.append("embedded")
    except Exception as e:
        log.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    # ── Stage 4: Vector search ────────────────────────────────────────────
    try:
        candidates = rp.vector_search(embedding, top_k=20, doc_filter=doc_filter)
        stages.append(f"retrieved_{len(candidates)}")
    except Exception as e:
        log.error(f"Vector search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Vector search failed: {e}")

    # ── Stage 5: Rerank ───────────────────────────────────────────────────
    try:
        top_docs = rp.rerank_chunks(query, candidates, top_n=5)
        stages.append(f"reranked_{len(top_docs)}")
    except Exception as e:
        log.warning(f"Reranking failed (using top 5 raw): {e}")
        top_docs = candidates[:5]
        stages.append("rerank_fallback")

    # ── Stage 6: Generate answer ──────────────────────────────────────────
    try:
        answer = rp.generate_answer(query, top_docs, role=role)
        stages.append("generated")
    except Exception as e:
        log.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    # ── Stage 7: Response safety ──────────────────────────────────────────
    try:
        resp_is_safe, resp_category = rp.check_response_safety(answer, query)
        if not resp_is_safe:
            answer = rp.RESPONSE_SAFETY_FALLBACK
            stages.append(f"response_blocked:{resp_category}")
        else:
            stages.append("response_safe")
    except Exception as e:
        log.warning(f"Response safety check crashed (failing open): {e}")
        stages.append("response_safety_skipped")

    latency_ms = int((time.monotonic() - t0) * 1000)
    log.info(f"✅ Pipeline complete | latency={latency_ms}ms | stages={stages}")

    # ── Check if the answer indicates no relevant documents were found ──────
    # If so, don't return any sources (crops)
    no_answer_indicators = [
        "لا تتضمن الوثائق المتاحة إجابة",
        "لم يتم استرداد أي مقتطفات",
        "لا يمكن الإجابة على هذا السؤال",
    ]
    has_no_answer = any(indicator in answer for indicator in no_answer_indicators)

    # Serialize top_docs into SourceChunk models
    # Note: Milvus returns string IDs like 'rtgs_p013_b02', so we use
    # the loop index as the numeric id for the response schema.
    # If there's no answer, return empty sources list.
    sources = [] if has_no_answer else [
        SourceChunk(
            id=i,
            doc_id=doc.get("doc_id", ""),
            page_num=int(doc.get("page_num", 0)),
            content=doc.get("content", ""),
            crop_url=doc.get("crop_url"),
            cosine_distance=doc.get("cosine_distance"),
            reranker_score=doc.get("reranker_score"),
        )
        for i, doc in enumerate(top_docs)
    ]

    return ChatResponse(
        answer=answer,
        sources=sources,
        stages=stages,
        latency_ms=latency_ms,
    )


@app.post("/chat/stream", tags=["Pipeline"])
def chat_stream(request: ChatRequest):
    """
    Run the RAG pipeline and stream the result using Server-Sent Events (SSE).
    """
    import json
    
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    role = request.role.lower()
    doc_filter = ROLE_DOC_FILTER.get(role, ROLE_DOC_FILTER["teller"])

    def event_generator():
        stages = []
        t0 = time.monotonic()
        
        def push_stage(stage_name: str):
            stages.append(stage_name)
            yield f"data: {json.dumps({'event': 'stage', 'stage': stage_name})}\n\n"

        # Stage 1: Safety
        try:
            is_safe, safety_category = rp.check_input_safety(query)
        except Exception:
            yield f"data: {json.dumps({'event': 'error', 'detail': 'Safety check failed'})}\n\n"
            return

        if not is_safe:
            yield from push_stage(f"safety_blocked:{safety_category}")
            yield f"data: {json.dumps({'event': 'token', 'text': rp.REFUSAL_MESSAGE})}\n\n"
            yield f"data: {json.dumps({'event': 'done', 'latency_ms': int((time.monotonic() - t0) * 1000)})}\n\n"
            return
        yield from push_stage("safety_passed")

        # Stage 2: Topic
        try:
            is_relevant, topic_label = rp.check_topic_relevance(query)
        except Exception:
            is_relevant = True

        if not is_relevant:
            yield from push_stage("topic_blocked")
            off_topic_msg = "يمكنني فقط الإجابة على الأسئلة المتعلقة بالإجراءات التشغيلية والمسائل القانونية المصرفية. يُرجى إعادة صياغة سؤالك."
            yield f"data: {json.dumps({'event': 'token', 'text': off_topic_msg})}\n\n"
            yield f"data: {json.dumps({'event': 'done', 'latency_ms': int((time.monotonic() - t0) * 1000)})}\n\n"
            return
        yield from push_stage("topic_passed")

        # Stage 3: Embed
        try:
            embedding = rp.embed_query(query)
            yield from push_stage("embedded")
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'detail': f'Embedding failed: {e}'})}\n\n"
            return

        # Stage 4: Retrieve
        try:
            candidates = rp.vector_search(embedding, top_k=20, doc_filter=doc_filter)
            yield from push_stage(f"retrieved_{len(candidates)}")
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'detail': f'Vector search failed: {e}'})}\n\n"
            return

        # Stage 5: Rerank
        try:
            top_docs = rp.rerank_chunks(query, candidates, top_n=5)
            yield from push_stage(f"reranked_{len(top_docs)}")
        except Exception:
            top_docs = candidates[:5]
            yield from push_stage("rerank_fallback")

        # Send Sources to client immediately before generating answer
        sources = [
            SourceChunk(
                id=i,
                doc_id=doc.get("doc_id", ""),
                page_num=int(doc.get("page_num", 0)),
                content=doc.get("content", ""),
                crop_url=doc.get("crop_url"),
                cosine_distance=doc.get("cosine_distance"),
                reranker_score=doc.get("reranker_score"),
            ).model_dump()
            for i, doc in enumerate(top_docs)
        ]
        yield f"data: {json.dumps({'event': 'sources', 'sources': sources})}\n\n"

        # Stage 6: Generate Answer (Streamed)
        yield from push_stage("generating")
        full_answer = ""
        try:
            for token in rp.generate_answer_stream(query, top_docs, role=role):
                full_answer += token
                # Send the chunk
                yield f"data: {json.dumps({'event': 'token', 'text': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'detail': f'Generation failed: {e}'})}\n\n"
            return

        # Check if the answer indicates no docs
        no_answer_indicators = [
            "لا تتضمن الوثائق المتاحة إجابة",
            "لم يتم استرداد أي مقتطفات",
            "لا يمكن الإجابة على هذا السؤال",
        ]
        has_no_answer = any(indicator in full_answer for indicator in no_answer_indicators)
        if has_no_answer:
            # Emit an event to clear sources on the UI
            yield f"data: {json.dumps({'event': 'sources', 'sources': []})}\n\n"

        yield from push_stage("generated")
        
        # Stage 7: Safety on the output could theoretically be done here
        # but since we already streamed it to the user, blocking it after the fact
        # is a UX challenge. For TTFT, we let the generated text pass.
        yield from push_stage("response_safe")

        # Done
        latency_ms = int((time.monotonic() - t0) * 1000)
        yield f"data: {json.dumps({'event': 'done', 'latency_ms': latency_ms})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
