# NBE Knowledge Assistant — Frontend Handover Guide

Welcome to the **NBE Knowledge Assistant** frontend codebase. This document is a comprehensive, technical handover designed to get the next developer or agent up to speed immediately. It outlines the codebase structure, design decisions, data communication flow, and key gotchas.

---

## 🏛️ 1. Codebase Overview & Dual Architecture

The frontend is a **React 19 + TypeScript + Vite** application designed for the internal operations of the **National Bank of Egypt (NBE)**. The design uses a sleek, HSL-tailored banking dark-mode palette aligned with NBE’s Navy and Gold branding. It is optimized for Arabic (RTL) reading and typography.

### ⚠️ Crucial Discovery: Dual Architecture Paths
The codebase contains **two distinct structures**, one of which is currently active and used in production, and another which is an alternative/unused implementation.

```mermaid
graph TD
    A[index.html / main.tsx] --> B[App.tsx]
    
    subgraph Active Production Structure
        B --> C[LoginScreen.tsx]
        B --> D[ChatScreen.tsx]
        D --> E[CitationPanel.tsx]
        D --> F[api.ts]
        F -- "POST /api/v1/chat/stream" --> G[SSE Streaming API]
    end

    subgraph Unused / Alternative Structure (Remnants or Refactor)
        H[components/Sidebar.tsx]
        I[components/ChatMessage.tsx]
        J[components/CitationsPanel.tsx]
        K[components/MessageInput.tsx]
        L[hooks/useChat.ts]
        M[api/ragApi.ts]
        N[types/api.ts]
        L --> M
        M -- "POST /api/v1/chat" --> O[Non-Streaming API]
    end
    
    style C fill:#0A1628,stroke:#C9A84C,stroke-width:2px,color:#fff
    style D fill:#0A1628,stroke:#C9A84C,stroke-width:2px,color:#fff
    style H fill:#162447,stroke:#4A5A78,stroke-width:1px,color:#8A9BBF
    style L fill:#162447,stroke:#4A5A78,stroke-width:1px,color:#8A9BBF
```

*   **Active Production Path** (Uses CSS Modules `*.module.css`):
    *   [App.tsx](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/App.tsx): Entry routing and session state.
    *   [LoginScreen.tsx](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/LoginScreen.tsx): Active employee portal login (Teller & Legal Counsel).
    *   [ChatScreen.tsx](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/ChatScreen.tsx): Main chat workspace utilizing SSE streaming and local token rendering.
    *   [CitationPanel.tsx](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/CitationPanel.tsx): Desktop-class sliding panel for document pages and OCR crops.
    *   [api.ts](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/api.ts): Backend API integration containing health checks and streaming client connection.
    *   [index.css](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/index.css): Master design system, CSS custom properties, and typography.
*   **Unused / Alternative Path** (Uses global styles in `index.css`):
    *   Located in `src/components/`, `src/hooks/`, `src/api/ragApi.ts`, and `src/types/api.ts`.
    *   These components are completely isolated and **not imported** in the active production code. They appear to be part of a refactoring attempt or an alternative non-streaming setup.
    *   `src/hooks/useChat.ts` utilizes the non-streaming `sendChat` function from `src/api/ragApi.ts`.

---

## ⚡ 2. Data Flow & Streaming Mechanics

The active implementation uses **Server-Sent Events (SSE)** via HTTP POST requests to achieve ultra-fast token-by-token streaming, complete with multi-stage reasoning logs.

### A. The Jitter Buffer & Typewriter Effect
To prevent visual layout shifts and stuttering caused by network packet jitter, [ChatScreen.tsx](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/ChatScreen.tsx) implements a **Jitter Buffer** for smooth typewriter rendering:
*   Incoming stream tokens are appended to a temporary string buffer (`tokenBuffer.current`).
*   A periodic rendering interval (~30ms or 33 fps) handles consumption from the buffer.
*   **Dynamic Speed Adjustment**: If the buffer size increases, the UI consumes characters faster (`Math.max(1, Math.ceil(bufferSize / 8))`) to prevent lag, while maintaining a smooth flow under slow connections.

### B. Streaming Callbacks & States
The `sendQueryStream()` function in [api.ts](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/api.ts) exposes five core event listeners:
1.  `onToken(token)`: Adds new tokens to the jitter buffer and hides the typing indicator.
2.  `onStage(stage)`: Records the current RAG stage (e.g., retrieval, safety checks). Flags like `safety_blocked`, `topic_blocked`, or `response_blocked` trigger a visual redirection state (`msg.role = 'blocked'`).
3.  `onSources(sources)`: Returns an array of `SourceChunk` assets retrieved by Milvus.
4.  `onDone(latency_ms)`: Concludes the stream and displays the query performance.
5.  `onError(error)`: Displays structural errors and stops processing.

---

## 🌐 3. Production Deployment & API Proxy Mappings

In production, the frontend is packaged using a multi-stage **Docker + Nginx** server ([Dockerfile](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/Dockerfile)) that acts as the single point of entry to secure and serve static assets.

### Nginx Routing Configuration
The Nginx configuration ([nginx.conf](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/nginx.conf)) listens on **port 3000** and directs traffic inside the Docker network.

| Client Route | Upstream Service | Description |
| :--- | :--- | :--- |
| `/api/` | `http://nbe-rag:8002/` | Proxies chat requests, streaming endpoints, and health checks to the RAG microservice. |
| `/nbe-crops/` | `http://nbe-minio:9000/nbe-crops/` | Reverse proxies image slices and bounding box clips from MinIO. |
| `/nbe-pages/` | `http://nbe-minio:9000/nbe-pages/` | Reverse proxies original full-page document images from MinIO. |

*   **SPA Support**: Includes a fallback route (`try_files $uri $uri/ /index.html;`) to avoid routing issues on browser refreshes.
*   **Asset Cache**: Implements aggressive caching (`Cache-Control: public, immutable`, 1-year expiry) for CSS, JS, and image assets.

---

## 🎨 4. NBE Custom Branding & RTL Support

The design matches NBE's corporate colors and caters to Egyptian banking scenarios:

*   **Theme Tokens** (defined in [index.css](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/index.css)):
    *   Gold Accent: `--nbe-gold: #C9A84C` (used for active highlights, boundaries, and badges).
    *   Navy Backgrounds: `--nbe-navy: #0A1628` / `--surface-0: #070E1C` (rich dark base).
    *   Typography: Arabic-optimized **Cairo** font loaded from Google Fonts.
*   **Right-To-Left (RTL)**: Configured in the core template (`<html lang="ar" dir="rtl">`). Textareas, inputs, and components are fully aligned for Arabic reading flows.
*   **Role Configuration**: Supports customized avatars, Arabic titles, and access rights.

---

## 🔍 5. Architectural Gotchas & Discrepancies

As the next developer, pay close attention to the following architectural discrepancies:

### 1. The Missing `manager` Role on the Login Page
*   **The Issue**: The backend API client ([api.ts](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/api.ts)) and alternate types ([types/api.ts](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/types/api.ts)) fully define three user roles: `'teller' | 'legal_counsel' | 'manager'`.
*   [ChatScreen.tsx](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/ChatScreen.tsx) contains complete visual branding and localized configurations for all three roles, including the `manager` role (`color: '#3FB950'`, `icon: '👔'`, `ar: 'المدير'`).
*   **However**, the active [LoginScreen.tsx](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/LoginScreen.tsx) only exposes two roles in its `ROLES` selection array: `teller` and `legal_counsel`.
*   **Action for Next Agent**: If full support for the `manager` role is required, you must add the `manager` configuration object to the `ROLES` array in `LoginScreen.tsx`.

### 2. Local Vite Development Proxy
*   **The Issue**: [vite.config.ts](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/vite.config.ts) is in its boilerplate state with no dev-server proxy configuration.
*   If you run the frontend locally outside Docker (`npm run dev`), requests to `/api/` will fail because they go to the Vite development port (e.g. `localhost:5173/api/`).
*   **Action for Next Agent**: When debugging or developing locally outside Docker, you should append a `server.proxy` block to `vite.config.ts` directing requests to `http://localhost:8003/api/` (where the RAG service port maps locally).

### 3. Docker Port Mappings vs. Runbook Guide
*   **The Issue**: In the root [deploy/docker-compose.yml](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/deploy/docker-compose.yml), the `rag-service` maps port **`8003:8002`** (exposing 8003 to the host, internal port 8002).
*   However, the operational runbook ([docs/runbook.md](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/docs/runbook.md)) instructs users to query and verify the service health via `curl http://localhost:8002/health`.
*   **Action for Next Agent**: When testing from the host system, query port `8003` (e.g., `curl http://localhost:8003/health`). The internal container port `8002` is only accessible inside the Docker bridge network.

### 4. Duplicate Type Specifications
*   There are two overlapping types files: [src/api.ts](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/api.ts) (which defines `SourceChunk`, `ChatResponse`, `UserRole`) and [src/types/api.ts](file:///Ubuntu/home/asoliman/projects/nbe-knowledge-assistant/frontend/src/types/api.ts) (which defines `SourceChunk`, `ChatResponse`, `Role`).
*   Make sure to edit both or consolidate them if a refactoring ticket is assigned.

---

## 🛠️ 6. How to Run and Build the Frontend

### Production Deployment
The frontend is fully managed in the main Docker Compose suite. To build and start:
```bash
# Run from the project root
docker compose -f deploy/docker-compose.yml --env-file deploy/config/.env up -d --build frontend
```

### Local Development
To run in hot-reload development mode:
```bash
cd frontend
npm install
npm run dev
```

---

Good luck with the development! This clean architecture provides a strong foundation for scaling the NBE Knowledge Assistant.
