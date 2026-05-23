"""
chain.py — LCEL RAG Chain Assembly
====================================
Assembles the full pipeline using LangChain Expression Language (LCEL):

  state → SafetyRunnable
        → RetrieverRunnable (Milvus ANN + NVIDIARerank + Topic Control)
        → AnswerRunnable    (ChatNVIDIA)
        → ResponseSafetyRunnable

Each Runnable receives the full state dict and returns an updated state dict.
This stateful approach lets any stage short-circuit by setting state["blocked"].

The chain is registered with LangServe to auto-expose:
  POST /rag/invoke
  POST /rag/stream
  POST /rag/batch
"""

from __future__ import annotations

import json
import logging
import re

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from rag_service.config import settings
from rag_service.retriever import RetrieverRunnable, html_to_text
from rag_service.safety import SafetyRunnable

log = logging.getLogger(__name__)


def _build_context_block(docs: list[Document]) -> str:
    """Render retrieved chunks as a numbered context block for the LLM."""
    parts = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        doc_info = f"[الوثيقة: {meta.get('doc_id', '?')} — صفحة {meta.get('page_num', '?')}]"
        clean_text = html_to_text(doc.page_content.strip())
        parts.append(f"مقتطف {i}\n{doc_info}\n{clean_text}")
    return "\n\n---\n\n".join(parts)


class AnswerRunnable(Runnable):
    """
    Generates the grounded answer using ChatNVIDIA.
    Reads `state['context_docs']` and `state['role']`.
    Writes `state['answer']`.
    """

    def invoke(self, state: dict, config: RunnableConfig | None = None) -> dict:
        if state.get("blocked"):
            state["answer"] = state.get("refusal", "")
            return state

        docs = state.get("context_docs", [])
        query = state["query"]
        role = state.get("role", "teller")

        if not docs:
            from rag_service.prompts import ROLE_REJECTION_MAP, GENERAL_REJECTION
            rejection = ROLE_REJECTION_MAP.get(role, GENERAL_REJECTION)
            state["answer"] = rejection
            return state

        context_block = _build_context_block(docs)
        prompt = get_rag_prompt(role)
        llm = ChatNVIDIA(
            model=settings.llm_model,
            base_url=settings.inference_base_url,
            api_key=settings.nvidia_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

        chain = prompt | llm | StrOutputParser()
        answer = chain.invoke({"context": context_block, "query": query})
        state["answer"] = answer.strip()
        log.info(f"Answer generated ({len(state['answer'])} chars)")
        return state


class ResponseSafetyRunnable(Runnable):
    """
    Checks the generated answer through NemoGuard content-safety.
    Replaces the answer with a fallback message if it fails.
    Fails open (passes through) on NIM errors.
    """

    def invoke(self, state: dict, config: RunnableConfig | None = None) -> dict:
        if state.get("blocked"):
            return state

        answer = state.get("answer", "")
        query = state.get("query", "")

        from langchain_nvidia_ai_endpoints import ChatNVIDIA as _NVIDIA
        llm = _NVIDIA(
            model=settings.safety_model,
            base_url=settings.safety_base_url,
            api_key=settings.nvidia_api_key,
        )
        try:
            response = llm.invoke([
                {"role": "user", "content": query},
                {"role": "assistant", "content": answer},
            ])
            raw = response.content.strip()
            try:
                verdict = json.loads(raw)
                verdict_lower = {k.lower(): v for k, v in verdict.items()}
                asst_safety = str(verdict_lower.get("assistant safety", "")).lower()
            except (json.JSONDecodeError, AttributeError):
                asst_safety = raw.lower().splitlines()[0].strip()

            high_risk = ["violence", "self-harm", "sexual", "hate", "criminal", "weapons"]
            if asst_safety != "safe" and any(kw in asst_safety for kw in high_risk):
                log.warning(f"Response safety BLOCKED: '{asst_safety}'")
                state["answer"] = REFUSAL_RESPONSE_UNSAFE
        except Exception as exc:
            log.warning(f"Response safety check failed (failing open): {exc}")

        return state


# ── Chain factory ──────────────────────────────────────────────────────────────

def build_rag_chain(doc_filter: list[str] | None = None) -> Runnable:
    """
    Build the full RAG LCEL chain for a given RBAC doc_filter.
    """
    chain = (
        SafetyRunnable()
        | RetrieverRunnable(doc_filter=doc_filter)
        | AnswerRunnable()
        | ResponseSafetyRunnable()
    )
    return chain
