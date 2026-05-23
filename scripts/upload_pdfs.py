#!/usr/bin/env python3
"""
upload_pdfs.py — Upload PDFs from PDF_SOURCE_DIR to MinIO and trigger
                 the full ingestion pipeline via the Orchestrator service.

Usage:
    pip install minio python-dotenv requests
    python scripts/upload_pdfs.py

What it does for each PDF found in PDF_SOURCE_DIR:
  1. Uploads the PDF to MinIO bucket "nbe-ingestion"
  2. POSTs a synthetic MinIO webhook event to the Orchestrator service
  3. The Orchestrator then:
       a. Converts PDF → page images (pypdfium2, 200 DPI)
       b. Calls Extraction Service  → Chandra OCR-2 on your local GPU
       c. Extraction Service calls Indexing Service → embeds via NVIDIA API
       d. Chunks land in Milvus, crops in MinIO

Run this once after `docker compose up -d` to index all your PDFs.
Re-running is safe: REINGESTION_POLICY=replace will overwrite existing docs.
"""

import os
import sys
import time
import json
import glob
import pathlib
import requests
from dotenv import load_dotenv

# ── Load env vars ──────────────────────────────────────────────────────────────
# Look for .env in deploy/config/ relative to this script's parent directory
SCRIPT_DIR = pathlib.Path(__file__).parent
ENV_PATH = SCRIPT_DIR.parent / "deploy" / "config" / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
    print(f"[config] Loaded .env from {ENV_PATH}")
else:
    print(f"[warn] .env not found at {ENV_PATH} — falling back to shell environment")

# ── Configuration ──────────────────────────────────────────────────────────────
PDF_SOURCE_DIR   = os.getenv("PDF_SOURCE_DIR", r"C:\Users\n.zakaria\Desktop\Data")
MINIO_ENDPOINT   = os.getenv("MINIO_HOST", "localhost:9000")   # host:port (no http://)
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET     = "nbe-ingestion"
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")

# ── Import minio ───────────────────────────────────────────────────────────────
try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:
    print("\n[error] 'minio' package not found.")
    print("  Install it with:  pip install minio python-dotenv requests")
    sys.exit(1)


def ensure_bucket(client: "Minio", bucket: str) -> None:
    """Create the bucket if it does not exist."""
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        print(f"[minio] Created bucket '{bucket}'")
    else:
        print(f"[minio] Bucket '{bucket}' already exists")


def upload_pdf(client: "Minio", local_path: pathlib.Path, bucket: str) -> str:
    """Upload a PDF to MinIO and return the object name."""
    object_name = f"pdfs/{local_path.name}"
    client.fput_object(
        bucket_name=bucket,
        object_name=object_name,
        file_path=str(local_path),
        content_type="application/pdf",
    )
    print(f"[minio] Uploaded → s3://{bucket}/{object_name}")
    return object_name


def trigger_orchestrator(object_name: str, bucket: str) -> dict:
    """
    POST a synthetic MinIO webhook event to the Orchestrator service.
    The Orchestrator handles the rest of the pipeline automatically.
    """
    # Build a minimal S3-compatible webhook payload (same structure MinIO sends)
    webhook_payload = {
        "Records": [
            {
                "eventName": "s3:ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": object_name},
                },
            }
        ]
    }

    url = f"{ORCHESTRATOR_URL}/webhook/minio"
    resp = requests.post(url, json=webhook_payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def poll_job(job_id: str, doc_name: str, timeout_minutes: int = 60) -> None:
    """Poll the orchestrator until the job finishes or times out."""
    url = f"{ORCHESTRATOR_URL}/v1/jobs/{job_id}"
    deadline = time.time() + timeout_minutes * 60
    last_status = None

    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            status = data.get("status", "unknown")

            if status != last_status:
                pct = data.get("progress_pct", 0)
                page = data.get("current_page", 0)
                total = data.get("total_pages", "?")
                print(f"  [{doc_name}] status={status}  page={page}/{total}  {pct:.0f}%")
                last_status = status

            if status == "complete":
                print(f"  [{doc_name}] ✓ Pipeline complete!")
                return
            if status == "failed":
                error = data.get("error", "unknown error")
                print(f"  [{doc_name}] ✗ Pipeline FAILED: {error}")
                return

        except requests.RequestException as e:
            print(f"  [{doc_name}] poll error: {e}")

        time.sleep(10)

    print(f"  [{doc_name}] ⚠ Timed out after {timeout_minutes} minutes")


def main():
    # ── 1. Find PDFs ────────────────────────────────────────────────────────
    source_dir = pathlib.Path(PDF_SOURCE_DIR)
    if not source_dir.exists():
        print(f"[error] PDF_SOURCE_DIR not found: {source_dir}")
        sys.exit(1)

    pdf_files = sorted(source_dir.glob("**/*.pdf"))
    if not pdf_files:
        print(f"[warn] No PDF files found in {source_dir}")
        sys.exit(0)

    print(f"\n[scan] Found {len(pdf_files)} PDF(s) in {source_dir}")
    for p in pdf_files:
        print(f"       • {p.name}")

    # ── 2. Connect to MinIO ─────────────────────────────────────────────────
    print(f"\n[minio] Connecting to {MINIO_ENDPOINT} ...")
    client = Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    ensure_bucket(client, MINIO_BUCKET)

    # ── 3. Check Orchestrator health ────────────────────────────────────────
    print(f"\n[orchestrator] Checking health at {ORCHESTRATOR_URL} ...")
    try:
        health = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=10)
        health.raise_for_status()
        print(f"[orchestrator] ✓ Running")
    except requests.RequestException as e:
        print(f"[error] Orchestrator not reachable: {e}")
        print("  Make sure all services are up:  docker compose up -d")
        sys.exit(1)

    # ── 4. Upload & trigger pipeline for each PDF ──────────────────────────
    print()
    jobs = []

    for pdf_path in pdf_files:
        print(f"[→] Processing: {pdf_path.name}")

        try:
            object_name = upload_pdf(client, pdf_path, MINIO_BUCKET)
            result = trigger_orchestrator(object_name, MINIO_BUCKET)
            print(f"     Orchestrator response: {result}")

            # The orchestrator returns job info in the records response
            # Poll based on the job queued
            jobs.append(pdf_path.name)

        except S3Error as e:
            print(f"  [error] MinIO upload failed: {e}")
        except requests.RequestException as e:
            print(f"  [error] Orchestrator trigger failed: {e}")

    print(f"\n[done] Triggered pipeline for {len(jobs)} document(s).")
    print("       Monitor progress:")
    print(f"         Orchestrator jobs: {ORCHESTRATOR_URL}/docs")
    print(f"         MinIO console:     http://localhost:9001")
    print(f"         Milvus (Attu):     http://localhost:8013")
    print(f"         Frontend:          http://localhost:3000")


if __name__ == "__main__":
    main()
