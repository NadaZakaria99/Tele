# Extraction Service

> **Status:** 📦 Reusable microservice — pull the image, mount a GPU, and POST your page images.

A FastAPI microservice that accepts Arabic (or multilingual) document page images and returns structured layout blocks with corrected bounding boxes and visual crop images.

Backed by **[Chandra OCR-2](https://huggingface.co/datalab-to/chandra-ocr-2)** (4B parameter multimodal model).

---

## What it does

| Input | Output |
|---|---|
| PNG page images (from PDF conversion) | `PageResult` JSON per page |
| Document metadata (doc_id, doc_type) | Per-block bounding boxes (original pixel coords) |
| | Cropped block images saved to shared volume |

Detected block types: `text`, `header`, `footer`, `table`, `figure`, `list`

---

## Requirements

| Requirement | Detail |
|---|---|
| GPU | NVIDIA GPU with ≥ 10 GB VRAM (tested on RTX 5090 32 GB) |
| CUDA | 12.4+ |
| HuggingFace token | Required — Chandra OCR-2 is a gated model |

---

## Quick Start

```bash
# 1. Copy and fill in environment variables
cp .env.example .env
# Edit .env: set HF_TOKEN

# 2. Run with Docker
docker run --gpus all \
  --env-file .env \
  -v /your/data:/data \
  -p 8000:8000 \
  your-registry/nbe-extraction-service:latest
```

---

## API Reference

### `GET /health`
Returns model load status and GPU info.

```json
{
  "status": "ok",
  "model_loaded": true,
  "gpu_available": true,
  "gpu_name": "NVIDIA GeForce RTX 5090",
  "vram_free_gb": 23.4
}
```

### `POST /v1/extract`
Submit a document for extraction. Returns a job ID immediately.

**Request:**
```json
{
  "doc_meta": {
    "doc_id": "rtgs",
    "doc_name": "rtgs_procedures.pdf",
    "doc_type": "SOP",
    "language": "ar",
    "total_pages": 52
  },
  "page_image_paths": [
    "/data/docs_images/rtgs/page_001.png",
    "/data/docs_images/rtgs/page_002.png"
  ],
  "forward_to_indexing": true
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "accepted",
  "doc_id": "rtgs",
  "total_pages": 52,
  "message": "Extraction job accepted. Poll GET /v1/jobs/{job_id} for status."
}
```

### `GET /v1/jobs/{job_id}`
Poll job status. When `status == "complete"`, the `pages` array contains the full `PageResult` objects.

---

## Coordinate System

Chandra OCR-2 outputs bounding boxes in a **0–1000 integer space** (not pixel coords, not normalized floats). This service converts them to original image pixel coordinates using:

```
pixel_x = (raw_val / 1000.0) * original_width
pixel_y = (raw_val / 1000.0) * original_height
```

This correction is built in — callers receive pixel-space bounding boxes directly.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `HF_TOKEN` | ✅ | — | HuggingFace access token |
| `CHANDRA_MODEL_ID` | | `datalab-to/chandra-ocr-2` | Model ID |
| `MAX_INFERENCE_DIM` | | `2000` | Max pixel dim for inference |
| `CROP_PADDING_PX` | | `8` | Padding around bboxes when cropping |
| `OUTPUT_DIR` | | `/data/pipeline_output` | Shared volume root |
| `INDEXING_SERVICE_URL` | | `http://indexing_service:8001` | Auto-forward destination |
| `PORT` | | `8000` | Server port |
