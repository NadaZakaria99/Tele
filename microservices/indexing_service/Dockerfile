# Indexing Service — CPU Dockerfile
#
# Build context: project root (nbe_knowledge_assistant/)
# Run from project root:
#   docker compose -f deploy/docker-compose.yml build indexing_service

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install shared schemas (path relative to project root build context)
COPY shared/nbe_schemas /app/shared/nbe_schemas
RUN uv pip install --system /app/shared/nbe_schemas

# Install service dependencies
WORKDIR /app/microservices/indexing_service
COPY microservices/indexing_service/pyproject.toml .

# Copy source before install so setuptools can find it
COPY microservices/indexing_service/src/ ./src/
RUN uv pip install --system -e ".[dev]"

ENV PYTHONPATH=/app/microservices/indexing_service/src

EXPOSE 8001

CMD ["python", "-m", "indexing_service.main"]
