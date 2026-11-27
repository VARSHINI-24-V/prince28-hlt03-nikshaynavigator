# Stage 1: Build the application
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
COPY data ./data
COPY prompts ./prompts
COPY alembic.ini ./

RUN uv sync --frozen --no-dev --no-install-project

RUN uv sync --frozen --no-dev


# Stage 2: Production runtime
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Update runtime OS packages to patch known vulnerabilities
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root application user
RUN groupadd --system app && \
    useradd --system --gid app --create-home app

# Copy application and dependencies from builder
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/migrations /app/migrations
COPY --from=builder --chown=app:app /app/scripts /app/scripts
COPY --from=builder --chown=app:app /app/data /app/data
COPY --from=builder --chown=app:app /app/prompts /app/prompts
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini

# Run as non-root user
USER app

# Git commit used to build this image
ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}

EXPOSE 8000

# Render provides PORT; use 8000 for local Docker runs
CMD ["sh", "-c", "uvicorn nikshaynavigator.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
