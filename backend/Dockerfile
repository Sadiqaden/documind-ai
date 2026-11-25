FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY demo_docs ./demo_docs
RUN pip install --upgrade pip && pip install .

# Run as an unprivileged user; data lives on a mounted volume.
RUN useradd --create-home --uid 10001 documind && mkdir -p /data && chown documind /data
USER documind
ENV DATA_DIR=/data DEMO_DOCS_DIR=/app/demo_docs
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
# Single worker: the rate limiter and vector index cache are in-process.
# --proxy-headers: trust X-Forwarded-For from the nginx frontend so rate limits are per client.
# The backend port is only exposed on the internal compose network.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
