# NBE Knowledge Assistant — Setup Guide (NVIDIA API Edition)

This guide walks you through running the full pipeline on **Windows** with your
own PDFs, using **NVIDIA's hosted API** instead of local NIM containers.

---

## What Changed From the Original

| Component | Original | This version |
|---|---|---|
| LLM (Llama 3.1) | Local NIM container (~30 GB VRAM) | NVIDIA API (`integrate.api.nvidia.com`) |
| Embedding model | Local NIM container | NVIDIA API |
| Reranking model | Local NIM container | NVIDIA API |
| OCR / Extraction | Local GPU (Chandra OCR-2) | **Still local** — no hosted equivalent |
| Data source | Pre-rendered PNG images | **Your PDFs** in `C:\Users\n.zakaria\Desktop\Data` |

You no longer need 60–80 GB of disk space for NIM model weights, and you do not
need to authenticate with `nvcr.io`. Your `NGC_API_KEY` is used directly as
the API key for all model calls.

---

## Prerequisites

- Windows 10/11 with **Docker Desktop** (WSL2 backend) installed
- **NVIDIA GPU** with the NVIDIA Container Toolkit (for extraction only)
- **Python 3.10+** (for the upload script)
- Your `NGC_API_KEY` (already in `.env.example`) and `HF_TOKEN`

---

## Step 1 — Clone & Configure

```bat
cd C:\Users\n.zakaria
git clone <repo-url> nbe-knowledge-assistant-main
cd nbe-knowledge-assistant-main

:: Copy and review the env file (values already filled in .env.example)
copy deploy\config\.env.example deploy\config\.env
```

Open `deploy\config\.env` and confirm:

```
DATA_DIR=C:/Users/n.zakaria/nbe-knowledge-assistant-main/data
PDF_SOURCE_DIR=C:/Users/n.zakaria/Desktop/Data
NGC_API_KEY=nvapi-...          <- your key
HF_TOKEN=hf_...                <- your HuggingFace token
```

> **Important — forward slashes in DATA_DIR**: Docker Desktop on Windows
> requires forward slashes (`/`) in volume paths, not backslashes.

---

## Step 2 — Create the Data Directories

```bat
mkdir data\docs_images
mkdir data\pipeline_output
mkdir data\legacy
mkdir data\orchestrator_temp
```

---

## Step 3 — Build and Start All Services

Run from the **project root** (`nbe-knowledge-assistant-main\`):

```bat
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env up -d --build
```

This starts (in dependency order):
1. `etcd`, `minio`, `milvus` — infrastructure
2. `attu` — Milvus web UI
3. `indexing-service` — waits for Milvus + MinIO
4. `extraction-service` — loads Chandra OCR-2 onto your GPU (~5 min first run)
5. `orchestrator-service` — listens for new PDFs
6. `rag-service` — query endpoint
7. `frontend` — chat UI at http://localhost:3000

Check everything is healthy:

```bat
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env ps
```

Wait until `extraction-service` shows **healthy** (it downloads the HuggingFace
model on first start — can take a few minutes).

---

## Step 4 — Install the Upload Script Dependencies

In a separate terminal (outside Docker):

```bat
pip install minio python-dotenv requests
```

---

## Step 5 — Ingest Your PDFs

```bat
python scripts/upload_pdfs.py
```

The script:
1. Scans `C:\Users\n.zakaria\Desktop\Data` for all `*.pdf` files
2. Uploads each PDF to MinIO (`nbe-ingestion` bucket)
3. Triggers the Orchestrator for each PDF — which:
   - Converts each PDF page → PNG at 200 DPI
   - Runs Chandra OCR-2 (your local GPU) to extract blocks and crops
   - Embeds chunks via NVIDIA API and upserts into Milvus

Processing time depends on document size. A 30-page Arabic PDF typically takes
2–4 minutes for OCR + indexing.

---

## Step 6 — Start Chatting

Open **http://localhost:3000** in your browser. The chat UI is connected to the
RAG service, which retrieves relevant chunks from Milvus and answers using
Llama 3.1 via the NVIDIA API.

---

## Monitoring

| Service | URL | What to check |
|---|---|---|
| Frontend (chat) | http://localhost:3000 | Main UI |
| MinIO console | http://localhost:9001 | Uploaded PDFs, crops |
| Milvus / Attu | http://localhost:8013 | Vector collection stats |
| Orchestrator jobs | http://localhost:8002/v1/jobs/{job_id} | Pipeline progress |
| Indexing catalog | http://localhost:8001/v1/catalog | Indexed documents |
| RAG health | http://localhost:8003/health | Query service status |

---

## Re-ingesting / Updating PDFs

Simply add new PDFs to `C:\Users\n.zakaria\Desktop\Data` and re-run:

```bat
python scripts/upload_pdfs.py
```

`REINGESTION_POLICY=replace` in `.env` ensures updated documents overwrite their
previous vectors in Milvus rather than duplicating them.

---

## Stopping the Stack

```bat
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env down
```

Add `-v` to also delete all stored data (Milvus vectors, MinIO files, etcd state):

```bat
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env down -v
```

---

## Troubleshooting

**`extraction-service` stays unhealthy for > 10 minutes**
The Chandra OCR-2 model is being downloaded from HuggingFace. Check logs:
```bat
docker logs nbe-extraction -f
```

**`upload_pdfs.py` — "Orchestrator not reachable"**
Services may still be starting. Wait 2–3 minutes and retry. You can check with:
```bat
docker compose -f deploy/docker-compose.yml ps
```

**NVIDIA API auth errors in indexing or RAG service**
Verify your `NGC_API_KEY` is valid at https://ngc.nvidia.com/ and that your
account has API catalog access enabled.

**`DATA_DIR` bind-mount errors on Windows**
Ensure the path uses forward slashes and the `data\` directory exists on disk:
```
DATA_DIR=C:/Users/n.zakaria/nbe-knowledge-assistant-main/data   ✓
DATA_DIR=C:\Users\n.zakaria\nbe-knowledge-assistant-main\data   ✗ (backslashes)
```
