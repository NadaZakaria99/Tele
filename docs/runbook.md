# NBE Knowledge Assistant — Operations Runbook

## Prerequisites

- Docker + Docker Compose (v2.20+)
- NVIDIA Container Toolkit installed (`nvidia-smi` works inside containers)
- NGC API key (for pulling NIM images)
- HuggingFace token (for Chandra OCR-2)
- ~100 GB free disk space (NIM model weights + data)

---

## First-Time Setup

```bash
# 1. Clone / enter the project
cd nbe_knowledge_assistant

# 2. Create the data directories
mkdir -p data/docs_images data/pipeline_output data/legacy

# 3. If migrating legacy data, copy from the old RAG project location:
cp -r /home/kareemetaam/work_projects/rag/my_work/pipeline_output data/legacy/
cp -r /home/kareemetaam/work_projects/rag/my_work/docs_images data/

# 4. Create the master env file
cp deploy/config/.env.example deploy/config/.env
# Edit deploy/config/.env — fill in NGC_API_KEY, HF_TOKEN

# 5. Log in to NGC (to pull NIM images)
docker login nvcr.io --username '$oauthtoken' --password $NGC_API_KEY

# 6. Create NIM cache directory
sudo mkdir -p /opt/nim/cache && sudo chmod 777 /opt/nim/cache
```

---

## Milestone 2: Index Existing Data (No Extraction Needed)

Start only the infrastructure + indexing service (skip NIMs and extraction):

```bash
cd deploy

# Start infrastructure
docker compose --env-file config/.env up -d etcd minio milvus

# Start the embedding NIM
docker compose --env-file config/.env up -d nim-embedding

# Start the indexing service
docker compose --env-file config/.env up -d indexing_service

# Trigger legacy import (indexes all docs from my_work/pipeline_output/)
curl -X POST http://localhost:8001/v1/index/legacy \
  -H "Content-Type: application/json" \
  -d '{
    "extractions_dir": "/data/legacy/pipeline_output/extractions"
  }'

# Poll until complete
curl http://localhost:8001/v1/jobs/<job_id>

# Verify catalog
curl http://localhost:8001/v1/catalog
```

---

## Milestone 3: Start the RAG Service

```bash
# Start remaining NIMs (LLM, reranker, safety)
docker compose --env-file config/.env up -d nim-llm nim-rerank nim-safety

# Wait for NIMs to be healthy (~3–5 min for model downloads on first run)
docker compose --env-file config/.env ps

# Start RAG service
docker compose --env-file config/.env up -d rag_service

# Test a query
curl -X POST http://localhost:8002/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "ما هو الإجراء المتبع لتحويل RTGS؟", "role": "teller"}'
```

---

## Milestone 4: Start the Frontend

```bash
docker compose --env-file config/.env up -d frontend
# Open http://localhost:3000
```

---

## Milestone 5: Full Pipeline (Extraction → Indexing → Query)

```bash
# Start all services including extraction_service
docker compose --env-file config/.env up -d

# Submit a new document for extraction
curl -X POST http://localhost:8000/v1/extract \
  -H "Content-Type: application/json" \
  -d '{
    "doc_meta": {
      "doc_id": "new_sop",
      "doc_name": "new_sop.pdf",
      "doc_type": "SOP",
      "language": "ar",
      "total_pages": 30
    },
    "page_image_paths": ["/data/docs_images/new_sop/page_001.png"],
    "forward_to_indexing": true
  }'
```

---

## Common Operations

### Check service health
```bash
curl http://localhost:8000/health   # extraction_service
curl http://localhost:8001/health   # indexing_service
curl http://localhost:8002/health   # rag_service
```

### Re-index a document
```bash
curl -X POST http://localhost:8001/v1/index/legacy \
  -d '{"doc_id": "rtgs", "extractions_dir": "/data/pipeline_output/extractions"}'
```

### View indexed documents
```bash
curl http://localhost:8001/v1/catalog | python3 -m json.tool
```

### Stop all services
```bash
docker compose --env-file config/.env down
```

### Wipe and restart from scratch
```bash
docker compose --env-file config/.env down -v  # removes volumes!
```
