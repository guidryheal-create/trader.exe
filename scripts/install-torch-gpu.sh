#!/bin/bash
# GPU Detection and PyTorch Installation Script
# This script detects GPU availability and installs the appropriate PyTorch wheel

set -e

echo "🔍 Checking for GPU availability..."

# Check for NVIDIA GPU
HAS_GPU=false
CUDA_VERSION=""

if command -v nvidia-smi >/dev/null 2>&1; then
    echo "✅ nvidia-smi found - GPU detected"
    HAS_GPU=true
    # Try to detect CUDA version from nvidia-smi
    if nvidia-smi --query-gpu=driver_version --format=csv,noheader >/dev/null 2>&1; then
        DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
        echo "   Driver version: $DRIVER_VERSION"
        # Map driver version to CUDA version (simplified)
        # Modern drivers (>=525) support CUDA 12.x
        # Older drivers may need CUDA 11.8
        CUDA_VERSION="cu121"  # Default to CUDA 12.1 for modern systems
    fi
elif [ -f /proc/driver/nvidia/version ]; then
    echo "✅ NVIDIA driver detected via /proc/driver/nvidia/version"
    HAS_GPU=true
    CUDA_VERSION="cu121"
fi

if [ "$HAS_GPU" = true ]; then
    echo "🚀 Installing CUDA-enabled PyTorch (CUDA $CUDA_VERSION)..."
    
    # Try CUDA 12.1 first (most common for modern GPUs)
    if uv pip install --system torch torchvision --index-url https://download.pytorch.org/whl/cu121 2>/dev/null; then
        echo "✅ CUDA 12.1 PyTorch installed successfully"
        exit 0
    fi
    
    # Fallback to CUDA 11.8
    echo "⚠️  CUDA 12.1 failed, trying CUDA 11.8..."
    if uv pip install --system torch torchvision --index-url https://download.pytorch.org/whl/cu118 2>/dev/null; then
        echo "✅ CUDA 11.8 PyTorch installed successfully"
        exit 0
    fi
    
    # Fallback to CPU version if CUDA installs fail
    echo "⚠️  CUDA PyTorch installation failed, installing CPU version"
    uv pip install --system torch torchvision || true
else
    echo "ℹ️  No GPU detected - CPU-only PyTorch will be installed via uv sync"
fi
