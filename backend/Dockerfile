FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# Install dependencies from lockfile
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# CPU Attention serving needs the hashed ONNX runtime subset, without replacing
# application Torch/tokenizers. pip check verifies the already installed dependencies.
COPY requirements-router-serving.lock ./
RUN pip install --no-cache-dir --no-deps --require-hashes -r requirements-router-serving.lock && pip check
COPY requirements-validation.lock ./
RUN pip install --no-cache-dir --no-deps --require-hashes -r requirements-validation.lock && pip check

# Copy application source code and configuration
COPY . .

# Install package in editable mode with development extras
RUN pip install --no-cache-dir --no-deps -e ".[dev]" && \
    chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
