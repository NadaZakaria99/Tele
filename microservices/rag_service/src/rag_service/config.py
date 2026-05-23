"""
config.py — RAG Service Configuration
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── NIM endpoints ─────────────────────────────────────────────────────────
    # All NIM services share the same base URL pattern on this host.
    # Override per-model if they run on different ports.
    nvidia_api_key: str = "no-key-needed-for-local-nim"
    inference_base_url: str = "http://nim-llm:8000/v1"
    embedding_base_url: str = "http://nim-embedding:8000/v1"
    rerank_base_url: str = "http://nim-rerank:8000/v1"
    safety_base_url: str = "https://integrate.api.nvidia.com/v1"

    # ── Models ────────────────────────────────────────────────────────────────
    embedding_model: str = "nvidia/llama-nemotron-embed-1b-v2"
    rerank_model: str = "nvidia/llama-nemotron-rerank-1b-v2"
    llm_model: str = "meta/llama-3.1-8b-instruct"
    safety_model: str = "nvidia/llama-3.1-nemoguard-8b-content-safety"
    topic_model: str = "nvidia/llama-3.1-nemoguard-8b-topic-control"

    # ── Milvus ────────────────────────────────────────────────────────────────
    milvus_host: str = "milvus"
    milvus_port: int = 19530
    milvus_collection: str = "nbe_documents"

    # ── Retrieval ─────────────────────────────────────────────────────────────
    retrieval_top_k: int = 20        # Candidates from Milvus before reranking
    rerank_top_n: int = 5            # Final chunks sent to the LLM

    # ── Generation ────────────────────────────────────────────────────────────
    llm_temperature: float = 0.1
    llm_max_tokens: int = 768

    # ── RBAC: role → allowed doc_ids (None = no filter = access all) ─────────
    # Serialised as JSON string in env: ROLE_DOC_FILTER='{"teller": ["rtgs"]}'
    role_doc_filter: dict[str, list[str] | None] = {
        "teller": ["rtgs"],
        "legal_counsel": None,
        "manager": None,
    }

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8002
    log_level: str = "info"


settings = Settings()  # type: ignore[call-arg]
