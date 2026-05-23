FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install shared schemas
COPY shared/nbe_schemas /app/shared/nbe_schemas
RUN uv pip install --system /app/shared/nbe_schemas

# Install service
WORKDIR /app/microservices/orchestrator_service
COPY microservices/orchestrator_service/pyproject.toml .
COPY microservices/orchestrator_service/src/ ./src/
RUN uv pip install --system -e .

ENV PYTHONPATH=/app/microservices/orchestrator_service/src

EXPOSE 8002

CMD ["python3", "-m", "orchestrator_service.main"]
