from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # MinIO Settings
    minio_endpoint: str = "nbe-minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_ingestion_bucket: str = "nbe-ingestion"

    # Service URLs
    extraction_service_url: str = "http://nbe-extraction:8000"
    indexing_service_url: str = "http://nbe-indexing:8001"

    # Pipeline Paths
    data_dir: Path = Path("/data")
    temp_dir: Path = Path("/data/orchestrator_temp")

settings = Settings()
