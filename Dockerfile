# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

WORKDIR /app

# Install dependencies in a separate layer so they cache across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the files the runtime needs. .dockerignore keeps secrets out.
COPY server.py index.html style.css app.js ./

# Create a non-root user and hand ownership to it. Running as non-root is
# required by Cloud Run security best practices and many corporate registries.
RUN groupadd --system --gid 1001 ecostep \
 && useradd  --system --uid 1001 --gid ecostep --no-create-home ecostep \
 && chown -R ecostep:ecostep /app
USER ecostep

EXPOSE 8080

# Cloud Run probes /healthz; the container is healthy iff Flask answers 200.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8080')+'/healthz',timeout=3).status==200 else 1)"

# `exec` form means gunicorn receives PID 1 signals (SIGTERM) cleanly.
CMD exec gunicorn \
  --bind ":${PORT}" \
  --workers 2 \
  --threads 4 \
  --worker-class gthread \
  --timeout 30 \
  --graceful-timeout 25 \
  --keep-alive 5 \
  --access-logfile - \
  --error-logfile - \
  --forwarded-allow-ips '*' \
  server:app
