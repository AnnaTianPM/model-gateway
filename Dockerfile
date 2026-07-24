FROM python:3.12-slim AS base

ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="Model Gateway"
LABEL org.opencontainers.image.description="LAN AI API Gateway with smart routing"
LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"
LABEL org.opencontainers.image.source="https://github.com/AnnaTianPM/model-gateway"
LABEL org.opencontainers.image.licenses="CC-BY-NC-4.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_VERSION=${APP_VERSION} \
    GIT_COMMIT=${GIT_COMMIT} \
    APP_VERSION_FILE=/app/VERSION

WORKDIR /app

# Install dependencies first (cache optimization)
COPY pyproject.toml ./
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx jinja2 pydantic pydantic-settings aiosqlite cryptography pyyaml python-multipart

# Copy source code
COPY . .

# Create non-root user
RUN useradd -r -s /bin/false gateway && \
    chown -R gateway:gateway /app
USER gateway

# Create data directory
RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
