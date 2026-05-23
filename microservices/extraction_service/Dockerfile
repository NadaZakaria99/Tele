# Extraction Service — GPU-enabled Docker image
# Base: CUDA 12.4 + Python 3.11 (supports RTX 5090 / Blackwell arch)
#
# Build context: project root (nbe_knowledge_assistant/)
# Run from project root:
#   docker compose -f deploy/docker-compose.yml build extraction_service

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-dev \
    python3-pip \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3 /usr/bin/python

# Install uv for fast dependency installation
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install shared schemas (path is relative to project root build context)
COPY shared/nbe_schemas /app/shared/nbe_schemas
RUN uv pip install --system /app/shared/nbe_schemas

# Install service dependencies
WORKDIR /app/microservices/extraction_service
COPY microservices/extraction_service/pyproject.toml .

# Copy source before install so setuptools can find it
COPY microservices/extraction_service/src/ ./src/
RUN uv pip install --system -e ".[dev]"

ENV PYTHONPATH=/app/microservices/extraction_service/src

EXPOSE 8000

CMD ["python3", "-m", "extraction_service.main"]
