# Frontend Dockerfile — multi-stage build
# Stage 1: Build the React app
# Stage 2: Serve with nginx (lightweight)

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

# Install pnpm (faster than npm for this monorepo pattern)
RUN npm install -g pnpm

# Copy package manifests first for layer caching
COPY package.json pnpm-lock.yaml* package-lock.json* ./

# Use pnpm if lockfile exists, otherwise npm
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    else npm install; fi

# Copy source
COPY . .

# Build — VITE_RAG_API_URL is set at runtime via nginx proxy, not baked in
RUN if [ -f pnpm-lock.yaml ]; then pnpm run build; else npm run build; fi

# ── Stage 2: Production Nginx ─────────────────────────────────────────────────
FROM nginx:1.27-alpine AS production

# Remove default nginx site
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config that:
#   - Serves static files from /usr/share/nginx/html
#   - Proxies /api/* to the rag_service (set via NGINX_UPSTREAM env var)
#   - Handles SPA routing (all 404s → index.html)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
