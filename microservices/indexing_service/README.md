# Indexing Service

> **Status:** 📦 Reusable microservice — pull the image and POST structured document pages to get them indexed.

A FastAPI microservice that takes structured document blocks (from the extraction service or your own pipeline), enriches them, generates embeddings via a local NVIDIA NIM, and indexes them into Milvus with visual assets stored in MinIO.

---

## What it does

| Input | Output |
|---|---|
| `PageResult` JSON objects (from extraction service) | Enriched chunks indexed in Milvus |
| OR: existing extraction directory (legacy import) | Crop PNGs + page images uploaded to MinIO |
| | Provenance entry in SQLite catalog |

---

## Quick Start

```bash
cp .env.example .env
# Edit .env: set NVIDIA_API_KEY, MILVUS_HOST, MINIO_* vars

docker run \
  --env-file .env \
  -v /your/data:/data \
  -p 8001:8001 \
  your-registry/nbe-indexing-service:latest
```

---

## API Reference

### `POST /v1/index`
Index pages received from the extraction service.

### `POST /v1/index/legacy`
Index from an existing extraction directory (first-run migration path).

**Request:**
```json
{
  "doc_id": "rtgs",
  "extractions_dir": "/data/legacy/pipeline_output/extractions"
}
```

### `GET /v1/jobs/{job_id}` — Poll job status
### `GET /v1/catalog` — List all indexed documents
### `GET /v1/catalog/{doc_id}` — Get catalog entry

---

## Enrichment Logic

Before embedding, every chunk is enriched:

1. **Header propagation** — section headers are prepended to text/list blocks: `[Section Header] text content`
2. **Noise filtration** — footers and blocks with < 3 words are dropped
3. **Table handling** — HTML table strings are embedded instead of flat text dumps
4. **Text splitting** — long text blocks split at `chunk_size=512` tokens with `chunk_overlap=50`

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `INFERENCE_BASE_URL` | ✅ | — | Local NIM or API Catalog base URL |
| `NVIDIA_API_KEY` | | `no-key` | API key (not needed for local NIM) |
| `MILVUS_HOST` | ✅ | `milvus` | Milvus hostname |
| `MINIO_ENDPOINT` | ✅ | `http://minio:9000` | MinIO endpoint |
| `MINIO_ACCESS_KEY` | ✅ | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | ✅ | `minioadmin` | MinIO secret key |
| `CATALOG_DB_PATH` | | `/data/pipeline_output/catalog.db` | SQLite catalog path |
| `REINGESTION_POLICY` | | `replace` | `replace` or `skip` |
| `CHUNK_SIZE` | | `512` | Target token count per chunk |
