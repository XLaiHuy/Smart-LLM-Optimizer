FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    SMARTLLM_ROOT=/app

COPY backend/pyproject.toml backend/requirements.lock ./
RUN pip install --no-cache-dir --default-timeout=180 --retries=10 --require-hashes -r requirements.lock
COPY backend/requirements-router-serving.lock backend/requirements-validation.lock ./
RUN pip install --no-cache-dir --no-deps --require-hashes -r requirements-router-serving.lock \
    && pip install --no-cache-dir --no-deps --require-hashes -r requirements-validation.lock \
    && pip check

COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/docker-entrypoint.sh ./
COPY config ./config

RUN pip install --no-cache-dir --no-deps -e . \
    && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
