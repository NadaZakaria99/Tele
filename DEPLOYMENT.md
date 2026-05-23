# NBE Knowledge Assistant: Complete Deployment Guide

This guide covers the end-to-end deployment of the NBE Knowledge Assistant, moving from a fresh server environment to a fully functional, containerized RAG platform.

## Prerequisites

Before starting, ensure your deployment server meets the following requirements:

*   **Hardware**: An NVIDIA GPU (e.g., RTX 5090 or equivalent) with at least 32GB of VRAM to host the NIM containers.
*   **Disk Space**: ~100 GB free disk space (to cache NIM model weights and store vector/document data).
*   **Software**: 
    *   Linux OS (Ubuntu 22.04+ recommended)
    *   Git
    *   Docker & Docker Compose (v2.20+)
    *   [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed (verify by running `nvidia-smi` inside a test container).
*   **Credentials**:
    *   **NVIDIA NGC API Key**: Obtainable from [NVIDIA NGC](https://ngc.nvidia.com/). Required to download NIM containers and models.
    *   **HuggingFace Access Token**: Obtainable from [Hugging Face Settings](https://huggingface.co/settings/tokens). Required for downloading the gated Chandra OCR-2 model.

---

## Step 1: Clone the Repository

Clone the project repository to your deployment machine and navigate into the project root:

```bash
git clone <your-repository-url> nbe_knowledge_assistant
cd nbe_knowledge_assistant
```

> **Important**: All subsequent commands in this guide **must** be executed from the `nbe_knowledge_assistant` project root directory.

---

## Step 2: Set Up Directories & Configuration

The application requires specific directories on the host system to store pipeline artifacts, databases, and configuration securely.

1. **Create the data directories**:
   ```bash
   mkdir -p data/docs_images data/pipeline_output data/legacy
   ```

2. **Prepare the NIM Cache Directory**:
   NIM containers download massive model weights. Caching them prevents re-downloading on every restart.
   ```bash
   sudo mkdir -p /opt/nim/cache
   sudo chmod 777 /opt/nim/cache
   ```

3. **Configure Environment Variables**:
   Copy the provided example configuration file and securely store your API keys.
   ```bash
   cp deploy/config/.env.example deploy/config/.env
   ```
   Open `deploy/config/.env` in your preferred text editor (`nano`, `vim`, etc.) and fill in your actual credentials:
   *   Set `NGC_API_KEY=your_ngc_api_key`
   *   Set `HF_TOKEN=your_huggingface_token`
   *   *(Optional)* Change `DATA_DIR` if you want to store data somewhere other than `/home/$USER/nbe_data`.

---

## Step 3: Authenticate Docker to NVIDIA Registry

To pull the enterprise NIM containers, you must authenticate your local Docker daemon with NVIDIA's container registry (`nvcr.io`).

```bash
docker login nvcr.io --username '$oauthtoken' --password $NGC_API_KEY
```
*(Note: Keep the username exactly as `'$oauthtoken'`. Replace `$NGC_API_KEY` with your actual key if not exported as a shell variable).*

---

## Step 4: Start Infrastructure Services

Bring up the foundational storage and database layers (Milvus vector database, etcd, and MinIO object storage).

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env up -d etcd minio milvus
```

Wait a few moments to ensure they are running stably. You can verify their health status:
```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env ps
```

---

## Step 5: Start NVIDIA NIMs (AI Models)

Next, spin up the local AI models. **Warning**: On the first run, this step will take several minutes to download ~60-80 GB of model weights.

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env up -d nim-embedding nim-rerank nim-llm nim-safety
```

You can monitor the download and startup progress:
```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env logs -f nim-llm
```
*(Press `Ctrl+C` to exit the logs. Proceed to the next step once the logs indicate the server is ready/listening).*

---

## Step 6: Start Microservices & Frontend

With the infrastructure and AI models running, you can now start the custom NBE microservices and the user interface.

```bash
# Start the backend API services
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env up -d extraction_service indexing_service rag_service

# Start the React frontend
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env up -d frontend
```

---

## Step 7: Verify the Deployment

Verify that all services are healthy and communicating properly.

1. **Check Service Health**:
   ```bash
   curl http://localhost:8000/health   # Extraction Service
   curl http://localhost:8001/health   # Indexing Service
   curl http://localhost:8002/health   # RAG Service
   ```
   *(All should return a `200 OK` JSON response indicating they are healthy).*

2. **Access the Application Interface**:
   Open your web browser and navigate to `http://localhost:3000` (or `http://<server-ip>:3000`). You should see the NBE Knowledge Assistant UI.

3. **Access MinIO Console (Optional)**:
   Navigate to `http://localhost:9001` (Default credentials: `minioadmin` / `minioadmin` unless changed in `.env`).

---

## Step 8: First-Time Data Ingestion

If you have legacy data to import, or wish to test the pipeline with a new document, follow these steps.

### Option A: Import Legacy Prototype Data
If you are migrating existing parsed data from the old monolithic prototype:

1. Copy the old data into the legacy folder:
   ```bash
   cp -r /path/to/old/data/* data/legacy/
   cp -r /path/to/old/docs_images/* data/docs_images/
   ```
2. Trigger the legacy ingestion endpoint:
   ```bash
   curl -X POST http://localhost:8001/v1/index/legacy \
     -H "Content-Type: application/json" \
     -d '{
       "extractions_dir": "/data/legacy/pipeline_output/extractions"
     }'
   ```

### Option B: Extract & Index a New Document
To run a document through the full GPU-accelerated extraction and indexing pipeline:

```bash
curl -X POST http://localhost:8000/v1/extract \
  -H "Content-Type: application/json" \
  -d '{
    "doc_meta": {
      "doc_id": "test_doc_01",
      "doc_name": "SOP_Banking_Procedures.pdf",
      "doc_type": "SOP",
      "language": "ar",
      "total_pages": 5
    },
    "page_image_paths": [
      "/data/docs_images/test_doc_01/page_001.png",
      "/data/docs_images/test_doc_01/page_002.png"
    ],
    "forward_to_indexing": true
  }'
```
*(Ensure the images exist at the specified paths within the `data/docs_images/` directory before running this command).*

---

## Common Management Commands

*   **View all running containers:**
    `docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env ps`
*   **Stop the application gracefully:**
    `docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env stop`
*   **Restart a specific service** (e.g., the frontend):
    `docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env restart frontend`
*   **Tear down the deployment** (Keeps data volumes intact):
    `docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env down`
*   **Complete Wipe** (Destroys all indexed data and databases. Use with caution!):
    `docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env down -v`
