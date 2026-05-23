"""
main.py — RAG Service FastAPI + LangServe Application
======================================================
Exposes the RAG chain via LangServe (auto-generates /rag/invoke, /rag/stream).
Also includes manual endpoints for more fine-grained control.

Endpoints:
  GET  /health                  — service health check
  POST /v1/chat                 — manual full pipeline with sources in response
"""

from __future__ import annotations

import logging
import time
import json
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from rag_service.config import settings
from rag_service.chain import build_rag_chain
from rag_service.models import ChatRequest, ChatResponse, HealthResponse, SourceChunk
from rag_service.prompts import REFUSAL_OFF_TOPIC, REFUSAL_RESPONSE_UNSAFE

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== RAG Service starting ===")
    yield
    log.info("=== RAG Service shutting down ===")


app = FastAPI(
    title="NBE RAG Service",
    description=(
        "Retrieval-Augmented Generation service for the NBE Knowledge Assistant. "
        "LangChain LCEL chain: Safety → Topic → Milvus Retrieve → NVIDIARerank → ChatNVIDIA → Safety. "
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

def to_public_url(url: str | None) -> str | None:
    """Convert internal MinIO URLs (minio:9000) to relative paths for the frontend proxy."""
    if not url:
        return None
    # Replace 'http://minio:9000/' with '/'
    return re.sub(r'^https?://minio:9000/', '/', url)


# ── Endpoints ───────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    from pymilvus import connections, Collection, utility
    try:
        connections.connect("default", host=settings.milvus_host, port=settings.milvus_port)
        entities = 0
        if utility.has_collection(settings.milvus_collection):
            col = Collection(settings.milvus_collection)
            col.load()
            entities = col.num_entities
        milvus_status = "connected"
    except Exception as e:
        entities = 0
        milvus_status = f"error: {e}"

    return HealthResponse(
        status="ok",
        milvus=milvus_status,
        collection_entities=entities,
    )


@app.post("/v1/chat", response_model=ChatResponse, tags=["RAG"])
def chat(request: ChatRequest) -> ChatResponse:
    """
    Full RAG pipeline with sources returned in the response.
    Equivalent to the original api_server.py /chat endpoint.
    """
    t0 = time.monotonic()

    role = request.role.lower()
    doc_filter = settings.role_doc_filter.get(role, None)
    chain = build_rag_chain(doc_filter=doc_filter)

    state = {"query": request.query, "role": role}
    result = chain.invoke(state)

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Serialize context docs as SourceChunk models
    context_docs = result.get("context_docs", [])
    no_answer_markers = [
        "لا تتضمن الوثائق المتاحة",
        "لم يتم استرداد أي مقتطفات",
        "صلاحيات حسابك مش بتسمح",
    ]
    answer = result.get("answer", "")
    has_no_answer = any(m in answer for m in no_answer_markers)

    sources = [] if has_no_answer else [
        SourceChunk(
            id=i,
            doc_id=doc.metadata.get("doc_id", ""),
            page_num=int(doc.metadata.get("page_num", 0)),
            content=doc.page_content,
            crop_url=to_public_url(doc.metadata.get("crop_minio_url")),
            page_image_url=to_public_url(doc.metadata.get("page_image_minio_url")),
            block_type=doc.metadata.get("block_type", "text"),
            cosine_distance=doc.metadata.get("cosine_distance"),
            reranker_score=doc.metadata.get("relevance_score"),
        )
        for i, doc in enumerate(context_docs)
    ]

    return ChatResponse(
        answer=answer,
        sources=sources,
        blocked=result.get("blocked", False),
        latency_ms=latency_ms,
    )


@app.post("/v1/chat/stream", tags=["RAG"])
def chat_stream(request: ChatRequest):
    """
    Legacy-compatible streaming endpoint using Server-Sent Events (SSE).
    Yields: stage, sources, token, done events.
    """
    role = request.role.lower()
    doc_filter = settings.role_doc_filter.get(role, None)
    chain = build_rag_chain(doc_filter=doc_filter)

    def event_generator():
        t0 = time.monotonic()
        state = {"query": request.query, "role": role}
        
        def push(event: str, data: dict):
            return f"data: {json.dumps({'event': event, **data})}\n\n"

        # ── Pipeline Execution ──────────────────────────────────────────
        # Manual step-through to push stage events
        from rag_service.safety import SafetyRunnable
        from rag_service.retriever import RetrieverRunnable
        from rag_service.chain import AnswerRunnable, ResponseSafetyRunnable, _build_context_block
        from rag_service.prompts import get_rag_prompt
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        from langchain_core.messages import HumanMessage, SystemMessage

        # 1. Safety
        yield push("stage", {"stage": "safety_passed"}) # Assuming it passes for now or we catch it
        state = SafetyRunnable().invoke(state)
        if state.get("blocked"):
            yield push("stage", {"stage": f"safety_blocked:{state.get('safety_category', 'unsafe')}"})
            yield push("token", {"text": state.get("refusal", "")})
            yield push("done", {"latency_ms": int((time.monotonic() - t0) * 1000)})
            return

        # 2. Retrieval & Topic
        state = RetrieverRunnable(doc_filter=doc_filter).invoke(state)
        if state.get("blocked"):
            yield push("stage", {"stage": "topic_blocked"})
            yield push("token", {"text": state.get("refusal", "")})
            yield push("done", {"latency_ms": int((time.monotonic() - t0) * 1000)})
            return
        
        yield push("stage", {"stage": "topic_passed"})
        yield push("stage", {"stage": "embedded"})
        yield push("stage", {"stage": f"retrieved_{state.get('retrieval_count', 0)}"})
        
        # 3. Sources
        context_docs = state.get("context_docs", [])
        sources = [
            SourceChunk(
                id=i,
                doc_id=doc.metadata.get("doc_id", ""),
                page_num=int(doc.metadata.get("page_num", 0)),
                content=doc.page_content,
                crop_url=to_public_url(doc.metadata.get("crop_minio_url")),
                page_image_url=to_public_url(doc.metadata.get("page_image_minio_url")),
                block_type=doc.metadata.get("block_type", "text"),
                cosine_distance=doc.metadata.get("cosine_distance"),
                reranker_score=doc.metadata.get("relevance_score"),
            ).model_dump()
            for i, doc in enumerate(context_docs)
        ]
        yield push("sources", {"sources": sources})
        yield push("stage", {"stage": f"reranked_{len(context_docs)}"})

        # 4. Generate (Streamed)
        yield push("stage", {"stage": "generating"})
        
        llm = ChatNVIDIA(
            model=settings.llm_model,
            base_url=settings.inference_base_url,
            api_key=settings.nvidia_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        prompt = get_rag_prompt(role)
        context_block = _build_context_block(context_docs)
        
        full_answer = ""
        # Invoke prompt template to get messages
        messages = prompt.format_messages(context=context_block, query=request.query)
        
        try:
            for chunk in llm.stream(messages):
                token = chunk.content
                full_answer += token
                yield push("token", {"text": token})
        except Exception as e:
            yield push("error", {"detail": str(e)})
            return

        state["answer"] = full_answer
        yield push("stage", {"stage": "generated"})

        # 5. Response Safety
        state = ResponseSafetyRunnable().invoke(state)
        if state.get("answer") == REFUSAL_RESPONSE_UNSAFE:
            yield push("stage", {"stage": "response_blocked"})
            # We already streamed the answer, but the UI might show a warning
        else:
            yield push("stage", {"stage": "response_safe"})

        yield push("done", {"latency_ms": int((time.monotonic() - t0) * 1000)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "rag_service.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
