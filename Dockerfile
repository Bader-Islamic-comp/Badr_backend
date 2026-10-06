# Reviewer demo image: the adult-operated synthetic development API
# (doc/development-boundary.md). Grounded answers, the model and speech stay off;
# no corpus, model or private data is copied in. See deploy/README.md.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml constraints-dev.txt ./
COPY src ./src
RUN pip install . -c constraints-dev.txt \
    && useradd --system --uid 10001 --no-create-home companion

USER companion

# Demo mode is the only mode, and it still refuses to start without
# COMPANION_DEMO_TOKEN (24+ ASCII characters), which the operator supplies.
ENV COMPANION_DEMO_MODE=true \
    COMPANION_RAG_ENABLED=false

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]

# 0.0.0.0 is inside the container only. Which host address the port is
# published on is decided by docker-compose.yml (loopback by default).
CMD ["uvicorn", "companion_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
