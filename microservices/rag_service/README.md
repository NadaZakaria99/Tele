# RAG Service

> **Status:** 📦 Reusable microservice — POST a question, get a grounded Arabic answer with visual citations.

A FastAPI + LangServe microservice implementing the full RAG query pipeline:

```
Safety (NemoGuard) → Topic Control → Embed → Milvus ANN → NVIDIARerank → ChatNVIDIA → Safety
```

Built with **LangChain LCEL** — the entire pipeline is a composable chain exposed via LangServe.

---

## Quick Start

```bash
cp .env.example .env
# Edit .env: set NIM endpoint URLs

docker run \
  --env-file .env \
  -p 8002:8002 \
  your-registry/nbe-rag-service:latest
```

---

## API Reference

### LangServe endpoints 

| Endpoint | Method | Description |
|---|---|---|
| `/rag/invoke` | POST | Synchronous query |
| `/rag/stream` | POST | Server-Sent Events streaming |
| `/rag/teller/invoke` | POST | Teller role (SOP docs only) |
| `/rag/legal_counsel/invoke` | POST | Legal counsel (all docs) |
| `/rag/playground` | GET | Interactive web playground |

### Manual endpoints

#### `POST /v1/chat`
Full pipeline with sources in the response body.

**Request:**
```json
{ "query": "ما هو الإجراء المتبع لتحويل RTGS؟", "role": "teller" }
```

**Response:**
```json
{
  "answer": "وفقاً لدليل إجراءات RTGS (صفحة 5)...",
  "sources": [
    {
      "id": 0,
      "doc_id": "rtgs",
      "page_num": 5,
      "content": "...",
      "crop_url": "http://minio:9000/nbe-crops/crops/rtgs/page_005/rtgs_p005_b01_table.png"
    }
  ],
  "blocked": false,
  "latency_ms": 1240
}
```

---

## RBAC — Role-Based Document Access

| Role | Access |
|---|---|
| `teller` | SOP documents only (`rtgs`, etc.) |
| `legal_counsel` | All documents |
| `manager` | All documents |

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `INFERENCE_BASE_URL` | ✅ | — | LLM NIM base URL |
| `EMBEDDING_BASE_URL` | ✅ | — | Embedding NIM base URL |
| `RERANK_BASE_URL` | ✅ | — | Reranking NIM base URL |
| `SAFETY_BASE_URL` | ✅ | — | NemoGuard NIM base URL |
| `MILVUS_HOST` | ✅ | `milvus` | Milvus hostname |
| `LLM_MODEL` | | `meta/llama-3.1-8b-instruct` | Generation model |
| `RETRIEVAL_TOP_K` | | `20` | Milvus candidate count |
| `RERANK_TOP_N` | | `5` | Chunks sent to LLM after reranking |
