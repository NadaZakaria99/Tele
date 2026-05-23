"""
config.py — Extraction Service Configuration
============================================
All settings are loaded from environment variables (or .env file).
Override any value by setting the corresponding env var.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Chandra OCR-2 ─────────────────────────────────────────────────────────
    # HuggingFace model ID for the OCR model
    chandra_model_id: str = "datalab-to/chandra-ocr-2"

    # HuggingFace token (required — model is gated)
    hf_token: str

    # Maximum pixel dimension fed to the model.
    # RTX 5090 32 GB can handle 2000px comfortably.
    # Lower to 1400 if you observe CUDA OOM on other machines.
    max_inference_dim: int = 2000

    # ── Crop generation ───────────────────────────────────────────────────────
    # Padding (in pixels) added around each bounding box when cropping
    crop_padding_px: int = 8

    # ── Output paths (inside the container / shared volume) ──────────────────
    # Crops and page-level JSONs are saved here; mounted as a Docker volume
    output_dir: str = "/data/pipeline_output"

    # ── Downstream service ────────────────────────────────────────────────────
    # After extraction completes, the service POSTs results to the indexing
    # service. Set to empty string to disable automatic forwarding.
    indexing_service_url: str = "http://nbe-indexing:8001"

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"


settings = Settings()  # type: ignore[call-arg]
