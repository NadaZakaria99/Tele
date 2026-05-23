"""
rag_pipeline.py — NBE Knowledge Assistant RAG Pipeline
=======================================================
Retrieval pipeline backed by Milvus vector database.

Pipeline stages:
  1. Input Safety Gate     — NemoGuard content-safety
  2. Topic Control Gate    — NemoGuard topic-control
  3. Query Embedding       — nvidia/llama-3.2-nv-embedqa-1b-v2
  4. Vector Search         — Milvus HNSW cosine similarity
  5. Semantic Reranking    — nvidia/llama-3.2-nv-rerankqa-1b-v2
  6. Answer Generation     — meta/llama-3.1-8b-instruct
  7. Response Safety Gate  — NemoGuard content-safety
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Union, Tuple, Iterator

import requests
from dotenv import load_dotenv
from pymilvus import connections, Collection

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
# Environment
# ---------------------------------------------------------------------------
load_dotenv()

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
if not NVIDIA_API_KEY:
    raise ValueError("Missing required environment variable: NVIDIA_API_KEY")

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# MinIO base URL for serving visual citation crops
MINIO_BASE_URL = os.environ.get("MINIO_BASE_URL", "http://localhost:9000")
MINIO_BUCKET   = os.environ.get("MINIO_BUCKET", "nbe-crops")

# Milvus connection settings
MILVUS_HOST       = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT       = os.environ.get("MILVUS_PORT", "19530")
MILVUS_COLLECTION = os.environ.get("MILVUS_COLLECTION", "nbe_documents")

log.info("✅ Environment variables loaded.")

# ---------------------------------------------------------------------------
# Milvus connection
# ---------------------------------------------------------------------------

def _connect_milvus() -> None:
    """Establish connection to the Milvus standalone instance."""
    connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
    log.info(f"✅ Milvus connected at {MILVUS_HOST}:{MILVUS_PORT}")


def test_db_connection() -> None:
    """Smoke-test the Milvus connection by loading the collection."""
    _connect_milvus()
    col = Collection(MILVUS_COLLECTION)
    col.load()
    log.info(f"✅ Milvus collection '{MILVUS_COLLECTION}' loaded OK — {col.num_entities} entities.")


# ---------------------------------------------------------------------------
# NVIDIA API wrapper
# ---------------------------------------------------------------------------

class NvidiaAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"NVIDIA API error {status_code}: {message}")


def nvidia_api_call(endpoint: str, payload: dict) -> dict:
    """POST to the NVIDIA NIM API and return the parsed JSON response."""
    url = f"{NVIDIA_BASE_URL}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=240)
        if response.status_code != 200:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise NvidiaAPIError(response.status_code, str(detail))
        log.info(f"✅ NVIDIA API '{endpoint}' succeeded.")
        return response.json()
    except requests.exceptions.RequestException as exc:
        log.error(f"❌ Network error calling NVIDIA API '{endpoint}': {exc}")
        raise


def nvidia_api_call_stream(endpoint: str, payload: dict) -> Iterator[str]:
    """POST to the NVIDIA NIM API with stream=True and yield tokens."""
    url = f"{NVIDIA_BASE_URL}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    payload["stream"] = True
    
    try:
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=240)
        if response.status_code != 200:
            raise NvidiaAPIError(response.status_code, response.text)
            
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith("data:"):
                    data_str = line_str[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        token = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if token:
                            yield token
                    except json.JSONDecodeError:
                        pass
    except requests.exceptions.RequestException as exc:
        log.error(f"❌ Streaming network error calling NVIDIA API '{endpoint}': {exc}")
        raise


# ---------------------------------------------------------------------------
# Stage 1 — Input safety check (NemoGuard)
# ---------------------------------------------------------------------------

SAFETY_MODEL = "nvidia/llama-3.1-nemoguard-8b-content-safety"
TOPIC_CONTROL_MODEL = "nvidia/llama-3.1-nemoguard-8b-topic-control"
# Arabic banking keywords that guarantee on-topic classification.
# Queries containing ANY of these terms skip the API call entirely.
_BANKING_KEYWORDS: list[str] = [
    # Financial instruments & returns
    "عوائد", "هامشية", "فائدة", "عائد", "أرباح", "ربح", "خسارة",
    "ائتمان", "مديونية", "دين", "قرض", "تمويل", "رصيد",
    # Settlement & payments
    "rtgs", "تسوية", "مدفوعات", "تحويل", "إيداع", "سحب", "ساتس",
    # Accounts & operations
    "حساب", "عملية", "إجراء", "إجراءات", "دليل", "مصطلح", "مصطلحات",
    "بند", "بنود", "فقرة", "مادة", "تعميم", "تعميمات", "دورية",
    "منتج", "خدمة", "منتجات", "خدمات",
    # Compliance & risk
    "kyc", "aml", "مخاطر", "امتثال", "توافق", "حوكمة", "رقابة",
    "غسيل", "تمويل الإرهاب",
    # Regulatory
    "بنك مركزي", "بنك أهلي", "nbe", "سياسة", "لائحة", "نظام",
    "ضمان", "رهن", "كفالة",
    # SOPs & docs
    "sop", "إجراء", "تشغيل", "موحد", "وثيقة", "مستند", "ملحق",
]

# Keywords that immediately trigger an off-topic block (sports, politics, casual)
_OFF_TOPIC_KEYWORDS: list[str] = [
    # Sports
    "مباراة", "نتيجة", "الاهلي", "الأهلي", "زمالك", "الزمالك", "كأس", 
    "بطولة", "دوري", "هدف", "فاز", "خسر", "تعادل",
    # Politics / Other
    "سياسة", "انتخابات", "رئيس", "حكومة", "أغنية", "فيلم", "مسلسل"
]

ALLOWED_TOPICS_DEFINITION = """The banking assistant covers ALL of these topics:

1. Banking SOPs (Standard Operating Procedures): account management, opening/closing,
   wire transfers, holds policy, overdrafts, payment systems, RTGS (real-time gross
   settlement), instant payments, KYC, AML, customer due diligence, fraud procedures,
   product guides, term glossaries, transaction limits, internal bank processes.

2. Financial & Banking Terms in Arabic: عوائد هامشية (marginal returns), فوائد
   (interest), ائتمان (credit), تسوية (settlement), مدفوعات (payments), حسابات جارية
   (current accounts), ودائع (deposits), قروض (loans), ضمانات (guarantees),
   رهن (mortgage), وثيقة (document), تعميم (circular), دورية (bulletin),
   مصطلحات (terminology), بنود (clauses), إجراءات (procedures).

3. Legal Banking Questions: regulatory compliance, banking law, CBE regulations,
   financial contracts, legal circulars, legal obligations of a bank.

ANYTHING related to how a bank operates, its documents, its procedures, its financial
products, or its legal framework is ON-TOPIC. When in doubt, assume on-topic.
"""


def check_topic_relevance(query: str) -> tuple[bool, str]:
    """
    Three-layer topic gate:
      Layer 1: Arabic banking keyword fast-path (no API call)
      Layer 2: NemoGuard topic-control API with enriched bilingual prompt
      Layer 3: Fail open — only block if confidently off-topic
    """
    query_lower = query.lower()

    # ── Layer 0: Negative keyword fast-path ───────────────────────────────
    for kw in _OFF_TOPIC_KEYWORDS:
        if kw in query_lower:
            log.warning(f"🚫 Topic fast-path BLOCKED (matched off-topic keyword: '{kw}')")
            return False, "off-topic"

    # ── Layer 1: Positive keyword fast-path ───────────────────────────────
    for kw in _BANKING_KEYWORDS:
        if kw in query_lower:
            log.info(f"✅ Topic fast-path PASSED (matched banking keyword: '{kw}')")
            return True, "on-topic"

    # ── Layer 2: NemoGuard API call ───────────────────────────────────────
    payload = {
        "model": TOPIC_CONTROL_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a topic control filter for an Egyptian banking assistant. "
                    "Your job is to decide if a query is related to banking. "
                    "Respond with exactly ONE word: 'on-topic' or 'off-topic'.\n\n"
                    f"{ALLOWED_TOPICS_DEFINITION}\n"
                    "IMPORTANT RULE: If you are even slightly unsure, respond 'on-topic'. "
                    "Only respond 'off-topic' for clearly unrelated subjects like "
                    "sports and matches (رياضة، مباريات، كرة قدم، الأهلي، الزمالك), "
                    "politics (سياسة), entertainment (ترفيه), cooking (طبخ), or personal advice."
                ),
            },
            {"role": "user", "content": query},
        ],
        "max_tokens": 20,
        "temperature": 0.0,
    }
    try:
        response = nvidia_api_call("chat/completions", payload)
        content = response["choices"][0]["message"]["content"].lower().strip()
        log.info(f"🔍 Topic control model replied: '{content}'")

        # ── Layer 3: Fail open — only block explicit off-topic ────────────
        if content.startswith("off"):
            log.warning("🚫 Topic control BLOCKED query")
            return False, "off-topic"
        # Any other response (on-topic, uncertain, etc.) → pass
        return True, "on-topic"
    except NvidiaAPIError as exc:
        log.warning(f"⚠️ Topic check error: {exc} — failing open.")
        return True, "on-topic"


def check_input_safety(query: str) -> tuple[bool, str]:
    """
    Run the query through NemoGuard content-safety.
    Returns (is_safe, category).
    """
    payload = {
        "model": SAFETY_MODEL,
        "messages": [{"role": "user", "content": query}],
    }
    try:
        response = nvidia_api_call("chat/completions", payload)
    except NvidiaAPIError as exc:
        log.error(f"❌ Safety check API error: {exc} — blocking query.")
        return False, "api_error"

    import json as _json
    raw_content: str = (
        response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    try:
        verdict = _json.loads(raw_content)
        verdict_lower = {k.lower(): v for k, v in verdict.items()}
        user_safety = str(verdict_lower.get("user safety", "")).lower()
        categories  = str(verdict_lower.get("safety categories", ""))
    except (_json.JSONDecodeError, AttributeError):
        user_safety = raw_content.lower().splitlines()[0].strip()
        categories  = ""

    if user_safety == "safe":
        log.info("🛡️  Input safety PASSED")
        return True, "safe"
    else:
        category = categories if categories else (user_safety or "unsafe")
        log.warning(f"🚫 Input safety FAILED — category: '{category}'")
        return False, category


# ---------------------------------------------------------------------------
# Stage 2 — Topic control gate
# ---------------------------------------------------------------------------

def check_topic_relevance(query: str) -> tuple[bool, str]:
    """
    Ensure the query is within the allowed banking scope.
    Returns (is_relevant, status).
    """
    payload = {
        "model": TOPIC_CONTROL_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a topic control filter for a banking assistant. "
                    "Your ONLY job is to decide whether a user query is relevant to the following topics. "
                    "Respond with exactly one word: 'on-topic' if relevant, 'off-topic' if not.\n\n"
                    f"Allowed topics:\n{ALLOWED_TOPICS_DEFINITION}\n\n"
                    "Important: Queries in Arabic about banking systems, real-time settlement (RTGS), "
                    "payment transfers, account operations, KYC, compliance, or any banking process ARE on-topic."
                ),
            },
            {"role": "user", "content": query},
        ],
        "max_tokens": 20,
        "temperature": 0.0,
    }
    try:
        response = nvidia_api_call("chat/completions", payload)
        content = response["choices"][0]["message"]["content"].lower().strip()
        if content.startswith("on"):
            return True, "on-topic"
        else:
            return False, "off-topic"
    except NvidiaAPIError as exc:
        log.warning(f"⚠️ Topic check error: {exc} — failing open.")
        return True, "on-topic"


# ---------------------------------------------------------------------------
# Stage 3 — Query embedding
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "nvidia/llama-3.2-nv-embedqa-1b-v2"
EMBEDDING_DIM   = 2048


def embed_query(query: str) -> List[float]:
    """Generate a 2048-dim dense vector for the user query."""
    payload = {
        "model": EMBEDDING_MODEL,
        "input": query,
        "input_type": "query",
        "encoding_format": "float",
    }
    response  = nvidia_api_call("embeddings", payload)
    embedding = response["data"][0]["embedding"]
    assert len(embedding) == EMBEDDING_DIM, f"Expected {EMBEDDING_DIM} dims, got {len(embedding)}"
    log.info(f"✅ Query embedded — {EMBEDDING_DIM} dims.")
    return embedding


# ---------------------------------------------------------------------------
# Stage 4 — Vector search (Milvus)
# ---------------------------------------------------------------------------

def vector_search(
    embedding: List[float],
    top_k: int = 20,
    doc_filter: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve top-k semantically similar chunks from Milvus.

    Args:
        embedding:   The query embedding vector.
        top_k:       Number of candidates to retrieve before reranking.
        doc_filter:  Optional list of doc_ids to restrict search to (RBAC).

    Returns:
        List of chunk dicts with 'id', 'content', 'doc_id', 'page_num',
        'crop_url', and 'cosine_distance'.
    """
    _connect_milvus()
    collection = Collection(MILVUS_COLLECTION)
    collection.load()

    search_params = {
        "metric_type": "COSINE",
        "params": {"ef": 64},
    }

    # Build optional doc_id filter expression for RBAC
    expr = None
    if doc_filter:
        quoted = [f'"{d}"' for d in doc_filter]
        expr = f"doc_id in [{', '.join(quoted)}]"
        log.info(f"🔒 RBAC filter active — allowed docs: {doc_filter}")

    results = collection.search(
        data=[embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        expr=expr,
        output_fields=["chunk_id", "doc_id", "page_num", "text", "crop_path"],
    )

    chunks = []
    for hit in results[0]:
        crop_path = hit.entity.get("crop_path") or ""
        # Build the full MinIO URL for the frontend to use directly
        crop_url = f"{MINIO_BASE_URL}/{MINIO_BUCKET}/{crop_path}" if crop_path else None

        chunks.append({
            "id":              hit.id,
            "content":         hit.entity.get("text", ""),
            "doc_id":          hit.entity.get("doc_id", ""),
            "page_num":        hit.entity.get("page_num", 0),
            "crop_path":       crop_path,
            "crop_url":        crop_url,
            "cosine_distance": float(1 - hit.distance),  # Milvus returns similarity, convert to distance
        })

    log.info(f"🔍 Retrieved {len(chunks)} chunks from Milvus.")
    return chunks


# ---------------------------------------------------------------------------
# Stage 5 — Semantic reranking
# ---------------------------------------------------------------------------

RERANK_MODEL = "nvidia/llama-3.2-nv-rerankqa-1b-v2"
RERANK_URL   = "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-3_2-nv-rerankqa-1b-v2/reranking"


def rerank_chunks(
    query: str,
    candidates: List[Dict[str, Any]],
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Rerank candidate chunks using a cross-encoder model.
    Attaches 'reranker_score' and returns the top-N.
    """
    if not candidates:
        return []

    payload = {
        "model": RERANK_MODEL,
        "query": {"text": query},
        "passages": [{"text": c["content"]} for c in candidates],
    }
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(RERANK_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            raise NvidiaAPIError(resp.status_code, resp.text)
        response = resp.json()
    except Exception as e:
        log.warning(f"⚠️ Reranking failed: {e} — falling back to vector search order.")
        return candidates[:top_n]

    rankings = response.get("rankings", [])
    rankings.sort(key=lambda x: x.get("logit", -float("inf")), reverse=True)

    reranked = []
    for rank in rankings[:top_n]:
        candidate = candidates[rank["index"]].copy()
        candidate["reranker_score"] = rank["logit"]
        reranked.append(candidate)

    log.info(f"🎯 Reranked to top {len(reranked)} chunks.")
    return reranked


# ---------------------------------------------------------------------------
# Stage 6 — Answer generation
# ---------------------------------------------------------------------------

GENERATOR_MODEL = "meta/llama-3.1-70b-instruct"


def html_to_text(html: str) -> str:
    """
    Convert HTML chunks (tables, headers) to clean readable plain text
    so the LLM can understand them without being confused by markup.

    Specifically handles:
      <h3>Header</h3>  → "[عنوان] Header"
      <table>...</table> → tab-separated rows
      All remaining tags → stripped
    """
    if not html.strip().startswith('<'):
        return html  # Already plain text — nothing to do

    # 1. Replace <h3> with a clear Arabic label prefix
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'[عنوان القسم]: \1\n', html, flags=re.DOTALL)

    # 2. Convert table rows to pipe-separated lines
    #    First: extract headers
    text = re.sub(r'<th[^>]*>(.*?)</th>', r'\1 | ', text, flags=re.DOTALL)
    #    Then: extract cells
    text = re.sub(r'<td[^>]*>(.*?)</td>', r'\1 | ', text, flags=re.DOTALL)
    #    Newline after each row
    text = re.sub(r'</tr>', '\n', text, flags=re.DOTALL)
    #    Remove remaining structural tags
    text = re.sub(r'<(table|thead|tbody|tr)[^>]*>', '', text, flags=re.DOTALL)
    text = re.sub(r'</(table|thead|tbody|tr)>', '', text, flags=re.DOTALL)

    # 3. Strip any remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # 4. Clean up excess whitespace / blank lines
    lines = [line.strip() for line in text.splitlines()]
    lines = [l for l in lines if l]
    return '\n'.join(lines)


SYSTEM_PROMPT_TEMPLATE = """أنت مساعد متخصص في البنك الأهلي المصري (NBE)، متخصص في الإجراءات التشغيلية الموحدة والتعميمات القانونية الصادرة عن البنك المركزي المصري.

مهمتك هي الإجابة على الأسئلة بناءً على مقتطفات الوثائق المقدَّمة إليك.

تعليمات مهمة:
- اعتمد في إجابتك على المحتوى الوارد في المقتطفات المرفقة.
- المقتطفات قد تحتوي على نصوص أو جداول أو قوائم — اقرأها بعناية واستخرج المعلومات منها مباشرةً.
- اذكر اسم الوثيقة ورقم الصفحة عند الاستشهاد بمعلومة.
- أجب باللغة العربية دائمًا.
- كن واضحًا وشاملًا: إذا وجدت قائمة أو جدولاً يُجيب على السؤال، فاعرض محتواه بشكل منظم.
- {rejection_instruction}
- لا تخترع تفاصيل أو سياسات غير موجودة في المقتطفات.
- ادخل في صلب الموضوع مباشرةً وبدون مقدمات. يُمنع منعًا باتًا استخدام عبارات تمهيدية مثل "بناءً على المقتطفات" أو "استنادًا إلى الوثائق" أو "وفقاً للنص المرفق"."""

TELLER_REJECTION = 'فقط إذا كانت المقتطفات لا تحتوي فعلاً على أي معلومة ذات صلة بالسؤال، يُمنع منعًا باتًا تقديم إجابة أو الاعتذار بشكل تقليدي. يجب عليك أن ترد حرفياً بالصيغة التالية مع استبدال الأقواس بموضوع السؤال: "بعتذر لحضرتك بس صلاحيات حسابك مش بتسمح بالاطلاع علي [موضوع السؤال]."'
GENERAL_REJECTION = 'فقط إذا كانت المقتطفات لا تحتوي فعلاً على أي معلومة ذات صلة بالسؤال، قل: "لا تتضمن الوثائق المتاحة إجابة على هذا السؤال."'


def generate_answer_stream(
    query: str,
    context_chunks: List[Dict[str, Any]],
    role: str = "teller",
    temperature: float = 0.1,
    max_tokens: int = 768,
) -> Iterator[str]:
    """
    Synthesize a grounded answer from the top-N reranked chunks.
    Yields chunks of text as they are generated by the LLM.
    """
    if not context_chunks:
        if role == "teller":
            yield "بعتذر لحضرتك بس صلاحيات حسابك مش بتسمح بالاطلاع علي تفاصيل هذا الموضوع."
        else:
            yield "لا توجد مقتطفات متاحة للإجابة على هذا السؤال في قاعدة البيانات."
        return

    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        reranker_info = (
            f"  [درجة الملاءمة: {chunk['reranker_score']:.3f}]"
            if isinstance(chunk.get("reranker_score"), float)
            else ""
        )
        doc_info = f"[الوثيقة: {chunk.get('doc_id', 'غير معروف')} — صفحة {chunk.get('page_num', '؟')}]"
        # Convert HTML → clean text for the LLM, but keep raw HTML in the dict for the UI
        clean_content = html_to_text(chunk['content'].strip())
        context_parts.append(
            f"مقتطف {i}{reranker_info}\n{doc_info}\n{clean_content}"
        )

    context_block = "\n\n---\n\n".join(context_parts)

    rejection = TELLER_REJECTION if role == "teller" else GENERAL_REJECTION
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(rejection_instruction=rejection)

    payload = {
        "model": GENERATOR_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"استخدم المقتطفات التالية للإجابة على السؤال:\n\n"
                    f"{context_block}\n\n---\n\n"
                    f"السؤال: {query}"
                ),
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 0.9,
    }

    log.info(f"🤖 Generating answer STREAM ({GENERATOR_MODEL}) with {len(context_chunks)} chunks …")
    yield from nvidia_api_call_stream("chat/completions", payload)
    log.info("✅ Answer streaming complete.")


def generate_answer(
    query: str,
    context_chunks: List[Dict[str, Any]],
    role: str = "teller",
    temperature: float = 0.1,
    max_tokens: int = 768,
) -> str:
    """
    Synthesize a grounded answer from the top-N reranked chunks.
    HTML content is converted to readable plain text before sending to the LLM.
    The raw HTML in context_chunks['content'] is intentionally NOT modified here
    so the frontend citation panel can still render tables and headers correctly.
    """
    if not context_chunks:
        if role == "teller":
            return "بعتذر لحضرتك بس صلاحيات حسابك مش بتسمح بالاطلاع علي تفاصيل هذا الموضوع."
        else:
            return "لا توجد مقتطفات متاحة للإجابة على هذا السؤال في قاعدة البيانات."

    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        reranker_info = (
            f"  [درجة الملاءمة: {chunk['reranker_score']:.3f}]"
            if isinstance(chunk.get("reranker_score"), float)
            else ""
        )
        doc_info = f"[الوثيقة: {chunk.get('doc_id', 'غير معروف')} — صفحة {chunk.get('page_num', '؟')}]"
        # Convert HTML → clean text for the LLM, but keep raw HTML in the dict for the UI
        clean_content = html_to_text(chunk['content'].strip())
        context_parts.append(
            f"مقتطف {i}{reranker_info}\n{doc_info}\n{clean_content}"
        )

    context_block = "\n\n---\n\n".join(context_parts)

    rejection = TELLER_REJECTION if role == "teller" else GENERAL_REJECTION
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(rejection_instruction=rejection)

    payload = {
        "model": GENERATOR_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"استخدم المقتطفات التالية للإجابة على السؤال:\n\n"
                    f"{context_block}\n\n---\n\n"
                    f"السؤال: {query}"
                ),
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 0.9,
    }

    log.info(f"🤖 Generating answer ({GENERATOR_MODEL}) with {len(context_chunks)} chunks …")
    response = nvidia_api_call("chat/completions", payload)
    answer = response["choices"][0]["message"]["content"].strip()
    log.info("✅ Answer generated.")
    return answer


# ---------------------------------------------------------------------------
# Stage 7 — Response safety check
# ---------------------------------------------------------------------------

def check_response_safety(response_text: str, original_query: str) -> tuple[bool, str]:
    """
    Check the generated response for unsafe content.
    Returns (is_safe, category).
    """
    payload = {
        "model": SAFETY_MODEL,
        "messages": [
            {"role": "user",      "content": original_query},
            {"role": "assistant", "content": response_text},
        ],
    }
    try:
        response = nvidia_api_call("chat/completions", payload)
    except NvidiaAPIError as exc:
        log.warning(f"⚠️ Response safety error: {exc} — failing open.")
        return True, "safe"

    import json as _json
    raw_content: str = (
        response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    try:
        verdict = _json.loads(raw_content)
        verdict_lower = {k.lower(): v for k, v in verdict.items()}
        assistant_safety = str(verdict_lower.get("assistant safety", "")).lower()
        categories = str(verdict_lower.get("safety categories", ""))
    except (_json.JSONDecodeError, AttributeError):
        assistant_safety = raw_content.lower().splitlines()[0].strip()
        categories = ""

    if assistant_safety == "safe":
        log.info("🛡️  Response safety PASSED")
        return True, "safe"

    category = categories if categories else (assistant_safety or "unsafe")
    high_severity = ["violence", "self-harm", "sexual", "hate", "criminal", "illegal", "weapons", "terrorism"]
    if any(kw in category.lower() for kw in high_severity):
        log.warning(f"🚫 Response safety FAILED — category: '{category}'")
        return False, category
    return True, category


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

REFUSAL_MESSAGE = (
    "عذرًا، لا يمكنني معالجة هذا الطلب. "
    "تم تصنيفه على أنه غير آمن من قِبَل نظام فلترة المحتوى."
)

RESPONSE_SAFETY_FALLBACK = (
    "تم إنشاء إجابة، لكنها تم تصنيفها على أنه قد تحتوي على محتوى غير مناسب "
    "ولا يمكن عرضها. يُرجى إعادة صياغة سؤالك."
)


def run_pipeline(
    query: str,
    return_sources: bool = False,
    doc_filter: List[str] | None = None,
) -> Union[str, Tuple[str, List[Dict[str, Any]]]]:
    """
    Full RAG pipeline: safety → topic → embed → retrieve → rerank → generate → safety.

    Args:
        query:          The user question.
        return_sources: If True, return (answer, top_docs) so the UI can show citations.
        doc_filter:     Optional list of doc_ids for RBAC (e.g. ["rtgs"] for tellers).

    Returns:
        answer string            when return_sources=False
        (answer, top_docs) tuple when return_sources=True
    """
    # Stage 1 — Input safety
    is_safe, category = check_input_safety(query)
    if not is_safe:
        log.warning(f"Pipeline halted — unsafe input: '{category}'")
        return (REFUSAL_MESSAGE, []) if return_sources else REFUSAL_MESSAGE

    # Stage 2 — Topic control
    is_relevant, topic_label = check_topic_relevance(query)
    if not is_relevant:
        off_topic_msg = (
            "يمكنني فقط الإجابة على الأسئلة المتعلقة بالإجراءات التشغيلية والمسائل القانونية المصرفية. "
            "يُرجى إعادة صياغة سؤالك."
        )
        return (off_topic_msg, []) if return_sources else off_topic_msg

    # Stage 3 — Embed
    try:
        embedding = embed_query(query)
    except Exception as e:
        err = f"[خطأ] فشل توليد التضمين: {e}"
        return (err, []) if return_sources else err

    # Stage 4 — Vector search (with optional RBAC filter)
    try:
        candidates = vector_search(embedding, top_k=20, doc_filter=doc_filter)
    except Exception as e:
        err = f"[خطأ] فشل البحث في قاعدة البيانات: {e}"
        return (err, []) if return_sources else err

    # Stage 5 — Rerank
    try:
        top_docs = rerank_chunks(query, candidates, top_n=5)
    except Exception as e:
        log.warning(f"Reranking failed, using top 5 raw results: {e}")
        top_docs = candidates[:5]

    # Stage 6 — Generate
    try:
        answer = generate_answer(query, top_docs)
    except Exception as e:
        err = f"[خطأ] فشل توليد الإجابة: {e}"
        return (err, top_docs) if return_sources else err

    # Stage 7 — Response safety
    resp_is_safe, resp_category = check_response_safety(answer, query)
    if not resp_is_safe:
        answer = RESPONSE_SAFETY_FALLBACK

    return (answer, top_docs) if return_sources else answer