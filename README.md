# NBE Knowledge Assistant — Microservices

> Production-grade RAG pipeline for Arabic banking documents. Built with LangChain, FastAPI, Milvus, and NVIDIA NIMs.

## Services

| Service | Port | Description |
|---|---|---|
| `extraction_service` | 8000 | Chandra OCR-2 extraction + crop generation (GPU) |
| `indexing_service` | 8001 | Enrich → Embed → Milvus → MinIO |
| `rag_service` | 8002 | Safety → Topic → Retrieve → Rerank → Generate |
| `frontend` | 3000 | React chat UI |
| `milvus` | 19530 | Vector database |
| `minio` | 9000/9001 | Object store (crops + page images) |

## Quick Start

```bash
cp deploy/config/.env.example deploy/config/.env
# Fill in NGC_API_KEY and HF_TOKEN

mkdir -p data/legacy
# If migrating legacy data, copy from the old RAG project location:    
cp -r /home/kareemetaam/work_projects/rag/my_work/pipeline_output data/legacy/
cp -r /home/kareemetaam/work_projects/rag/my_work/docs_images data/

docker compose --env-file deploy/config/.env up -d etcd minio milvus nim-embedding indexing_service
# Then: POST to localhost:8001/v1/index/legacy to index existing data
# See docs/runbook.md for the full step-by-step guide
```

## Documentation

- [`docs/runbook.md`](docs/runbook.md) — Full operations guide
- [`microservices/extraction_service/README.md`](microservices/extraction_service/README.md) — Extraction service API
- [`microservices/indexing_service/README.md`](microservices/indexing_service/README.md) — Indexing service API
- [`microservices/rag_service/README.md`](microservices/rag_service/README.md) — RAG service API

## Architecture

```
[PDFs] → extraction_service (GPU) → indexing_service → [Milvus + MinIO]
                                                              ↓
                          [React frontend] ← rag_service ← [Query]
```
