"""
retriever.py — LangChain Milvus Retriever with RBAC
====================================================
Wraps the shared Milvus collection as a LangChain retriever.
Applies role-based document access control via Milvus expr filters.
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document
from langchain_milvus import Milvus
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings, NVIDIARerank
from langchain_core.runnables import Runnable, RunnableConfig

import re
from rag_service.config import settings

log = logging.getLogger(__name__)

# ── Arabic Banking Keywords for Topic Control ──────────────────────────────
_BANKING_KEYWORDS: list[str] = [
    "عوائد", "هامشية", "فائدة", "عائد", "أرباح", "ربح", "خسارة",
    "ائتمان", "مديونية", "دين", "قرض", "تمويل", "رصيد",
    "rtgs", "تسوية", "مدفوعات", "تحويل", "إيداع", "سحب", "ساتس",
    "حساب", "عملية", "إجراء", "إجراءات", "دليل", "مصطلح", "مصطلحات",
    "بند", "بنود", "فقرة", "مادة", "تعميم", "تعميمات", "دورية",
    "منتج", "خدمة", "منتجات", "خدمات",
    "kyc", "aml", "مخاطر", "امتثال", "توافق", "حوكمة", "رقابة",
    "غسيل", "تمويل الإرهاب",
    "بنك مركزي", "بنك أهلي", "nbe", "سياسة", "لائحة", "نظام",
    "ضمان", "رهن", "كفالة",
    "sop", "إجراء", "تشغيل", "موحد", "وثيقة", "مستند", "ملحق",
]

_OFF_TOPIC_KEYWORDS: list[str] = [
    "مباراة", "نتيجة", "الاهلي", "الأهلي", "زمالك", "الزمالك", "كأس", 
    "بطولة", "دوري", "هدف", "فاز", "خسر", "تعادل",
    "سياسة", "انتخابات", "رئيس", "حكومة", "أغنية", "فيلم", "مسلسل"
]

ALLOWED_TOPICS_DEFINITION = """The banking assistant covers ALL of these topics:
1. Banking SOPs (Standard Operating Procedures): wire transfers, payment systems, RTGS, KYC, AML, product guides.
2. Financial & Banking Terms in Arabic: عوائد هامشية, فوائد, ائتمان, تسوية, مدفوعات, حسابات, ودائع, قروض.
3. Legal Banking Questions: regulatory compliance, banking law, CBE regulations, legal circulars.
ANYTHING related to how a bank operates, its documents, its procedures, its financial products, or its legal framework is ON-TOPIC.
"""

def html_to_text(html: str) -> str:
    """Clean up HTML chunks (tables, headers) for LLM consumption."""
    if not html.strip().startswith('<'):
        return html
    # Replace headers
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'[عنوان القسم]: \1\n', html, flags=re.DOTALL)
    # Convert table cells to pipe-separated
    text = re.sub(r'<th[^>]*>(.*?)</th>', r'\1 | ', text, flags=re.DOTALL)
    text = re.sub(r'<td[^>]*>(.*?)</td>', r'\1 | ', text, flags=re.DOTALL)
    text = re.sub(r'</tr>', '\n', text, flags=re.DOTALL)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    return "\n".join(l.strip() for l in text.splitlines() if l.strip())


def get_embeddings() -> NVIDIAEmbeddings:
    return NVIDIAEmbeddings(
        model=settings.embedding_model,
        base_url=settings.embedding_base_url,
        api_key=settings.nvidia_api_key,
        truncate="END",
    )


def get_reranker() -> NVIDIARerank:
    return NVIDIARerank(
        model=settings.rerank_model,
        base_url=settings.rerank_base_url,
        api_key=settings.nvidia_api_key,
        top_n=settings.rerank_top_n,
    )


def get_milvus_retriever(
    doc_filter: list[str] | None = None,
    top_k: int | None = None,
) -> Milvus:
    """
    Return a configured Milvus retriever.

    Args:
        doc_filter:  List of doc_ids to restrict search to (RBAC).
                     None = no filter (access to all documents).
        top_k:       Number of candidates to retrieve before reranking.
    """
    embeddings = get_embeddings()
    k = top_k or settings.retrieval_top_k

    search_kwargs: dict = {"k": k}
    if doc_filter:
        quoted = ", ".join(f'"{d}"' for d in doc_filter)
        search_kwargs["expr"] = f"doc_id in [{quoted}]"
        log.info(f"RBAC filter active: doc_id in [{quoted}]")

    vectorstore = Milvus(
        embedding_function=embeddings,
        collection_name=settings.milvus_collection,
        connection_args={
            "uri": f"http://{settings.milvus_host}:{settings.milvus_port}",
        },
        vector_field="embedding",
        text_field="text",
        auto_id=False,
        drop_old=False,
    )
    return vectorstore.as_retriever(search_kwargs=search_kwargs)


class RetrieverRunnable(Runnable):
    """
    LangChain Runnable that:
      1. Performs a 3-layer topic relevance check.
      2. Retrieves top-K candidates from Milvus (with RBAC filter).
      3. Reranks them using NVIDIARerank.
    """

    def __init__(self, doc_filter: list[str] | None = None) -> None:
        self.doc_filter = doc_filter

    def _check_topic(self, query: str) -> tuple[bool, str]:
        """Three-layer topic gate (Keywords + NemoGuard)."""
        query_lower = query.lower()
        # Layer 0: Negative keywords
        for kw in _OFF_TOPIC_KEYWORDS:
            if kw in query_lower:
                log.warning(f"🚫 Topic fast-path BLOCKED: '{kw}'")
                return False, "off-topic"
        # Layer 1: Positive keywords
        for kw in _BANKING_KEYWORDS:
            if kw in query_lower:
                log.info(f"✅ Topic fast-path PASSED: '{kw}'")
                return True, "on-topic"
        # Layer 2: External Topic check via NVIDIA API
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        llm = ChatNVIDIA(
            model=settings.topic_model,
            base_url=settings.safety_base_url,
            api_key=settings.nvidia_api_key,
            temperature=0.0,
            max_tokens=20,
        )
        sys_msg = (
            "You are a topic control filter for an Egyptian Banking Knowledge Assistant. "
            "Respond with exactly ONE word: 'on-topic' or 'off-topic'.\n\n"
            f"{ALLOWED_TOPICS_DEFINITION}\n"
            "If the query is related to banking, procedures, or NBE, respond 'on-topic'. "
            "If it is about sports, general history, or politics, respond 'off-topic'."
        )
        try:
            resp = llm.invoke([{"role": "system", "content": sys_msg}, {"role": "user", "content": query}])
            content = resp.content.lower().strip()
            log.info(f"Topic API verdict: '{content}' for query: '{query}'")
            return (not "off-topic" in content), content
        except Exception as e:
            log.warning(f"Topic check error: {e} — failing open.")
            return True, "on-topic"

    def invoke(self, state: dict, config: RunnableConfig | None = None) -> dict:
        if state.get("blocked"):
            return state

        query = state["query"]
        
        # 1. Topic Control
        is_relevant, topic_status = self._check_topic(query)
        state["topic_status"] = topic_status
        if not is_relevant:
            state["blocked"] = True
            state["refusal"] = "يمكنني فقط الإجابة على الأسئلة المتعلقة بالإجراءات المصرفية. يُرجى إعادة صياغة سؤالك."
            return state

        # 2. Retrieval
        retriever = get_milvus_retriever(doc_filter=self.doc_filter)
        reranker = get_reranker()

        try:
            candidates: list[Document] = retriever.invoke(query)
            log.info(f"Retrieved {len(candidates)} candidates")
            state["retrieval_count"] = len(candidates)
        except Exception as exc:
            log.error(f"Milvus retrieval failed: {exc}")
            state["context_docs"] = []
            return state

        # 3. Reranking
        try:
            reranked: list[Document] = reranker.compress_documents(candidates, query)
            log.info(f"Reranked to {len(reranked)} top docs")
            state["context_docs"] = reranked
        except Exception as exc:
            log.warning(f"Reranking failed: {exc}")
            state["context_docs"] = candidates[: settings.rerank_top_n]

        return state
