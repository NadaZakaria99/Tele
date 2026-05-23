import logging
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from nbe_schemas.pipeline import OrchestratorJob, PipelineStatus
from orchestrator_service.pipeline import run_ingestion_pipeline, _jobs, get_job

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="NBE Orchestrator Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global queue for sequential processing
_queue = asyncio.Queue()

async def worker():
    """Sequential consumer that pulls jobs from the queue one by one."""
    log.info("Ingestion worker started.")
    while True:
        job_id, object_key = await _queue.get()
        try:
            log.info(f"Worker starting Job: {job_id}")
            await run_ingestion_pipeline(job_id, object_key)
        except Exception as e:
            log.error(f"Worker error in Job {job_id}: {e}")
        finally:
            _queue.task_done()
            log.info(f"Worker finished Job: {job_id}")

@app.on_event("startup")
async def startup_event():
    # Start the sequential background worker
    asyncio.create_task(worker())

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/v1/jobs/{job_id}", response_model=OrchestratorJob)
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/webhook/minio")
async def minio_webhook(request: Request):
    """
    MinIO Webhook endpoint. Receives S3-compatible event notifications.
    """
    try:
        payload = await request.json()
        log.info(f"Received MinIO webhook: {payload}")
        
        # MinIO payload structure has "Records"
        records = payload.get("Records", [])
        if not records:
            return {"status": "ignored", "reason": "no records"}

        for record in records:
            event_name = record.get("eventName")
            # We only care about object creation
            if not event_name or "ObjectCreated" not in event_name:
                continue

            bucket = record["s3"]["bucket"]["name"]
            object_key = record["s3"]["object"]["key"]
            
            # Basic validation
            if not object_key.lower().endswith(".pdf"):
                log.warning(f"Ignoring non-PDF file: {object_key}")
                continue

            # Create Job
            job_id = str(uuid.uuid4())
            doc_id = object_key.split("/")[-1].replace(".pdf", "").replace(" ", "_")
            doc_name = object_key.split("/")[-1]
            
            job = OrchestratorJob(
                job_id=job_id,
                doc_id=doc_id,
                doc_name=doc_name,
                status=PipelineStatus.ACCEPTED
            )
            _jobs[job_id] = job
            
            # Queue for sequential processing
            log.info(f"Queueing ingestion for {doc_name} (Job: {job_id})")
            await _queue.put((job_id, object_key))

        return {"status": "accepted", "jobs_queued": len(records)}

    except Exception as e:
        log.exception("Error processing MinIO webhook")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
