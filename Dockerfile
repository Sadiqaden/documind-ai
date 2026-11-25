# Single-container image (frontend + backend) for hosts like Render, Railway or Fly.io.
# docker-compose.yml keeps the two-container nginx setup for local use.

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --upgrade pip && pip install .
COPY backend/demo_docs ./demo_docs
COPY --from=frontend /frontend/dist ./static

RUN useradd --create-home --uid 10001 documind && mkdir -p /data && chown documind /data
USER documind

# Safe public defaults: free retrieval-only answers, read-only demo library.
ENV DATA_DIR=/data \
    DEMO_DOCS_DIR=/app/demo_docs \
    FRONTEND_DIST_DIR=/app/static \
    LLM_PROVIDER=extractive \
    DEMO_MODE=true \
    PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/api/health')"
# Hosts set $PORT. --proxy-headers so rate limits see the visitor's IP, not the host's proxy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
