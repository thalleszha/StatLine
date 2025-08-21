# syntax=docker/dockerfile:1.7

############################
# Base layer
############################
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Minimal OS deps; add build tools only in build-targets if/when needed
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /app

############################
# Runtime from PyPI (default)
############################
# Build args let you pick extras and version on the fly:
#   docker build --target runtime-pypi --build-arg STATLINE_EXTRAS=cli-pretty .
#   docker build --target runtime-pypi --build-arg STATLINE_VERSION==1.0.0 .
FROM base AS runtime-pypi

ARG STATLINE_EXTRAS=""        # e.g., "sheets" or "cli-pretty" or "sheets,cli-pretty"
ARG STATLINE_VERSION=""       # e.g., "==1.0.0" or empty for latest

# Compute a pip requirement of the form: statline[extras]==X
# Hadolint/SH: keep simple; extras may be empty
RUN set -eux; \
    PKG="statline${STATLINE_VERSION}"; \
    if [ -n "${STATLINE_EXTRAS}" ]; then PKG="statline[${STATLINE_EXTRAS}]${STATLINE_VERSION}"; fi; \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "${PKG}"

USER app

# Quick smoke check on container start (optional health via CMD)
# Default entrypoint to the CLI; override with `docker run … statline score …`
ENTRYPOINT ["statline"]
CMD ["--help"]

############################
# Runtime from source (dev/CI)
############################
# Use this target if building the image from the current repo checkout.
# Example:
#   docker build --target runtime-src .
FROM base AS runtime-src

# Optional: system build deps only if your deps need compilation
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Copy just metadata first for better cache (edit includes if you have a lock file)
COPY pyproject.toml README.md LICENSE ./
# If you package adapter defs / data, copy them early for cache too:
# COPY statline/core/adapters/defs/ statline/core/adapters/defs/
# COPY statline/data/ statline/data/

# Install with optional extras during dev:
#   docker build --target runtime-src --build-arg EXTRAS=dev .
ARG EXTRAS=""
RUN pip install --no-cache-dir --upgrade pip && \
    if [ -n "${EXTRAS}" ]; then \
      pip install --no-cache-dir ".[${EXTRAS}]"; \
    else \
      pip install --no-cache-dir . ; \
    fi || true  # first pass may fail before sources are copied; we’ll reinstall below

# Copy the rest of the source and reinstall (editable or normal)
COPY statline/ statline/
RUN if [ -n "${EXTRAS}" ]; then \
      pip install --no-cache-dir --upgrade ".[${EXTRAS}]" ; \
    else \
      pip install --no-cache-dir --upgrade . ; \
    fi

USER app
ENTRYPOINT ["statline"]
CMD ["--help"]
