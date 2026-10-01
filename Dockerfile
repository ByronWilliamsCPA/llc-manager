# Multi-stage Dockerfile for LLC Manager
# Optimized for production with security best practices and minimal image size

# =============================================================================
# Stage 1: Builder - Install dependencies
# =============================================================================
# Hardened Python from the GHCR mirror; the -dev variant has a shell and apt.
# Source tag: ghcr.io/byronwilliamscpa/dhi-python:3.12-debian13-dev
FROM ghcr.io/byronwilliamscpa/dhi-python@sha256:e473be33548ba1374f21d4bdda388f6a10b32291f5dca61f1752e1c32d2fd76f AS builder

# Set working directory
WORKDIR /app

# Install system dependencies for building Python packages
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install UV for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d /uv /usr/local/bin/uv

# Copy dependency files (README.md required by hatchling to build the project)
COPY pyproject.toml uv.lock README.md ./

# Install dependencies to a virtual environment
# This creates .venv/ which we'll copy to the final stage
RUN uv sync --frozen --no-dev --extra api --no-install-project

# Copy application code
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev --extra api

# =============================================================================
# Stage 2: Runtime - Minimal production image
# =============================================================================
# Distroless runtime (no shell, no package manager) matching the builder's
# Python path, so the copied virtualenv resolves its interpreter unchanged.
# Source tag: ghcr.io/byronwilliamscpa/dhi-python:3.12-debian13
FROM ghcr.io/byronwilliamscpa/dhi-python@sha256:16d369bd4628a6a02210e93e7a6c1c646782e3d19492a799c3d437b29a5543ce

# Metadata labels (OCI standard)
LABEL org.opencontainers.image.title="LLC Manager"
LABEL org.opencontainers.image.description="A web application for managing LLC entities, tracking compliance dates, ownership structures, and associated documentation"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.authors="Byron Williams <byron@williamscpa.com>"
LABEL org.opencontainers.image.url="https://github.com/ByronWilliamsCPA/llc-manager"
LABEL org.opencontainers.image.source="https://github.com/ByronWilliamsCPA/llc-manager"
LABEL org.opencontainers.image.licenses="MIT"

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=65532:65532 /app/.venv /app/.venv

# Copy application code
COPY --chown=65532:65532 . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src

# Switch to the image's built-in non-root user (UID/GID 65532)
USER 65532:65532

# Expose port (default for FastAPI/web apps)
EXPOSE 8000
# Health check - adjust endpoint based on your app
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health/live', timeout=2).status == 200 else 1)"]

# Default command - run web server
CMD ["uvicorn", "llc_manager.main:app", "--host", "0.0.0.0", "--port", "8000"]
# =============================================================================
# Build Arguments (optional, for build-time configuration)
# =============================================================================
# Example:
# ARG BUILD_ENV=production
# ENV ENVIRONMENT=${BUILD_ENV}

# =============================================================================
# Multi-architecture support
# =============================================================================
# Build for multiple platforms:
# docker buildx build --platform linux/amd64,linux/arm64 -t myimage:latest .
