import logging
import asyncio
import httpx
import pypdfium2 as pdfium
from pathlib import Path
from datetime import datetime, timezone
from nbe_schemas.pipeline import OrchestratorJob, PipelineStatus
from orchestrator_service.config import settings
from orchestrator_service.minio_client import minio_client

log = logging.getLogger(__name__)

# Shared state for jobs
_jobs: dict[str, OrchestratorJob] = {}

def get_job(job_id: str) -> OrchestratorJob | None:
    return _jobs.get(job_id)

async def run_ingestion_pipeline(job_id: str, object_name: str, doc_type: str = "SOP"):
    """
    Background worker task to process a PDF from MinIO through the full pipeline.
    """
    job = _jobs[job_id]
    try:
        # 1. Fetch
        job.status = PipelineStatus.FETCHING
        job.updated_at = datetime.now(timezone.utc)
        pdf_path = settings.temp_dir / job.doc_id / f"{job.doc_id}.pdf"
        minio_client.download_object(object_name, pdf_path)

        # 2. Convert PDF to Images
        job.status = PipelineStatus.CONVERTING
        job.updated_at = datetime.now(timezone.utc)
        images_dir = settings.data_dir / "docs_images" / job.doc_id
        images_dir.mkdir(parents=True, exist_ok=True)
        
        pdf = pdfium.PdfDocument(str(pdf_path))
        job.total_pages = len(pdf)
        image_paths = []
        
        for i in range(job.total_pages):
            page = pdf[i]
            # Render at 200 DPI for good OCR quality
            bitmap = page.render(scale=2.7) 
            pil_image = bitmap.to_pil()
            img_name = f"page_{i+1:03d}.png"
            img_path = images_dir / img_name
            pil_image.save(img_path)
            image_paths.append(str(img_path))
            
            job.current_page = i + 1
            job.progress_pct = (i + 1) / job.total_pages * 20  # First 20% is conversion
            job.updated_at = datetime.now(timezone.utc)

        # 3. Call Extraction Service
        job.status = PipelineStatus.EXTRACTING
        job.updated_at = datetime.now(timezone.utc)
        
        async with httpx.AsyncClient(timeout=600.0) as client:
            extract_payload = {
                "doc_meta": {
                    "doc_id": job.doc_id,
                    "doc_name": job.doc_name,
                    "doc_type": doc_type,
                    "language": "ara",
                    "total_pages": job.total_pages
                },
                "page_image_paths": image_paths,
                "forward_to_indexing": True
            }
            
            log.info(f"Triggering extraction for {job.doc_id}...")
            resp = await client.post(
                f"{settings.extraction_service_url}/v1/extract",
                json=extract_payload
            )
            
            if resp.status_code != 202:
                raise RuntimeError(f"Extraction service failed: {resp.text}")
            
            extraction_job = resp.json()
            ext_job_id = extraction_job["job_id"]
            
            # Poll extraction service for progress
            while True:
                status_resp = await client.get(
                    f"{settings.extraction_service_url}/v1/jobs/{ext_job_id}"
                )
                ext_status = status_resp.json()
                
                if ext_status["status"] == "complete":
                    break
                if ext_status["status"] == "failed":
                    raise RuntimeError(f"Extraction failed: {ext_status.get('error')}")
                
                # Update orchestrator progress (mapped to 20%-95% range)
                # Note: extraction_service doesn't give % yet, so we just wait
                await asyncio.sleep(5)

        # 4. Finalize
        job.status = PipelineStatus.COMPLETE
        job.progress_pct = 100.0
        job.updated_at = datetime.now(timezone.utc)
        log.info(f"Pipeline complete for {job.doc_id}")

    except Exception as e:
        log.exception(f"Pipeline failed for {job.doc_id}")
        job.status = PipelineStatus.FAILED
        job.error = str(e)
        job.updated_at = datetime.now(timezone.utc)
