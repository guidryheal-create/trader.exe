# Dockerfile for Polymarket Trading System - API Service
# CAMEL-based trading system with enhanced pipelines
FROM ghcr.io/astral-sh/uv:python3.11-bookworm

LABEL maintainer="Agentic Trading Team"
LABEL description="CAMEL-based Agentic Trading API with Phase 5 Workspace Memory"

WORKDIR /app

# Environment for reliable installs
ENV UV_HTTP_TIMEOUT=300 \
    UV_CACHE_DIR=/tmp/uv-cache \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install NVIDIA Container Toolkit dependencies for GPU detection
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy configuration files
COPY pyproject.toml requirements.txt uv.lock ./

# Copy GPU detection scripts
COPY scripts/install-torch-gpu.sh /tmp/install-torch-gpu.sh
COPY scripts/check-gpu-runtime.sh /app/scripts/check-gpu-runtime.sh
RUN chmod +x /tmp/install-torch-gpu.sh /app/scripts/check-gpu-runtime.sh

# Copy all application code
COPY . .

# Build argument to force GPU/CUDA installation
# Usage: docker build --build-arg INSTALL_CUDA=true ...
ARG INSTALL_CUDA=false

# Detect GPU availability and install appropriate PyTorch wheel
# If INSTALL_CUDA is set, install CUDA-enabled PyTorch regardless of detection
RUN if [ "$INSTALL_CUDA" = "true" ]; then \
        echo "🚀 Force installing CUDA-enabled PyTorch (INSTALL_CUDA=true)"; \
        uv pip install --system torch torchvision --index-url https://download.pytorch.org/whl/cu121 || \
        uv pip install --system torch torchvision --index-url https://download.pytorch.org/whl/cu118 || \
        echo "⚠️  CUDA PyTorch installation failed"; \
    else \
        echo "🔍 Checking for GPU at build time..."; \
        /tmp/install-torch-gpu.sh || echo "ℹ️  GPU detection at build time inconclusive, will use default PyTorch"; \
    fi

# Use uv sync to install dependencies (without scheduler extras - API service doesn't need apscheduler)
# This creates a proper project environment that uv run will recognize
# If torch was already installed by the GPU script, uv sync will skip it
# Using --frozen to ensure exact versions from uv.lock are installed
RUN uv sync --no-dev --frozen

# Create necessary directories
RUN mkdir -p /app/config /app/logs /app/data

# Set environment variables for relative imports
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose port for API
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the agentic API service using uv
# Using direct module path since PYTHONPATH=/app and imports use 'from api.', 'from core.', etc.
CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
