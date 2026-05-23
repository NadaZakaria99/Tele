import logging
from pathlib import Path
from minio import Minio
from orchestrator_service.config import settings

log = logging.getLogger(__name__)

class MinioClient:
    def __init__(self):
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(settings.minio_ingestion_bucket):
            log.info(f"Creating bucket: {settings.minio_ingestion_bucket}")
            self.client.make_bucket(settings.minio_ingestion_bucket)

    def download_object(self, object_name: str, dest_path: Path):
        """Download an object from the ingestion bucket to a local path."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.fget_object(
            settings.minio_ingestion_bucket,
            object_name,
            str(dest_path)
        )
        log.info(f"Downloaded {object_name} to {dest_path}")

minio_client = MinioClient()
