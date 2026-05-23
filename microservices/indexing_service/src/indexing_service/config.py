"""
config.py — Indexing Service Configuration
==========================================
All settings loaded from environment variables / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── NIM / NVIDIA AI Endpoints ──────────────────────────────────────────────
    # Point to local NIM containers in production, or NVIDIA API Catalog for dev
    inference_base_url: str = "http://nim-embedding:8000/v1"
    nvidia_api_key: str = "no-key-needed-for-local-nim"

    embedding_model: str = "nvidia/llama-3.2-nv-embedqa-1b-v2"
    embedding_dim: int = 2048
    embedding_batch_size: int = 32

    # ── Milvus ────────────────────────────────────────────────────────────────
    milvus_host: str = "milvus"
    milvus_port: int = 19530
    milvus_collection: str = "nbe_documents"

    # ── MinIO / Object Store ──────────────────────────────────────────────────
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_crops: str = "nbe-crops"
    minio_bucket_pages: str = "nbe-page-images"

    # ── SQLite Catalog ────────────────────────────────────────────────────────
    catalog_db_path: str = "/data/pipeline_output/catalog.db"

    # ── Shared data volume ────────────────────────────────────────────────────
    # Must match the volume mount in docker-compose.yml
    data_dir: str = "/data"
    pipeline_output_dir: str = "/data/pipeline_output"

    # ── Chunking ──────────────────────────────────────────────────────────────
    # Target token count for text chunks (tables are never split)
    chunk_size: int = 512
    chunk_overlap: int = 50

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "info"

    # ── Re-ingestion policy ───────────────────────────────────────────────────
    # "replace" = delete all vectors for doc_id before inserting new ones
    # "skip"    = do nothing if doc_id already exists in catalog
    reingestion_policy: str = "replace"


settings = Settings()  # type: ignore[call-arg]
