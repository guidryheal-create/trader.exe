#!/bin/bash
# Runtime GPU Detection Script
# This script checks for GPU availability at runtime and verifies PyTorch can use it

set -e

echo "🔍 Checking GPU availability at runtime..."

# Check for NVIDIA GPU
HAS_GPU=false
CUDA_AVAILABLE=false

if command -v nvidia-smi >/dev/null 2>&1; then
    echo "✅ nvidia-smi found"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader | head -1
    HAS_GPU=true
elif [ -f /proc/driver/nvidia/version ]; then
    echo "✅ NVIDIA driver detected"
    cat /proc/driver/nvidia/version | head -1
    HAS_GPU=true
fi

if [ "$HAS_GPU" = true ]; then
    echo "🚀 GPU detected - checking PyTorch CUDA support..."
    
    # Check if PyTorch can see CUDA
    python3 << 'PYTHON_SCRIPT'
import sys
try:
    import torch
    print(f"✅ PyTorch version: {torch.__version__}")
    if torch.cuda.is_available():
        print(f"✅ CUDA available: {torch.cuda.is_available()}")
        print(f"✅ CUDA version: {torch.version.cuda}")
        print(f"✅ GPU count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"   GPU {i}: {torch.cuda.get_device_name(i)}")
        sys.exit(0)
    else:
        print("⚠️  PyTorch installed but CUDA not available")
        print("   This may mean CPU-only PyTorch is installed")
        sys.exit(1)
except ImportError:
    print("❌ PyTorch not installed")
    sys.exit(1)
PYTHON_SCRIPT
    
    if [ $? -eq 0 ]; then
        CUDA_AVAILABLE=true
        echo "✅ PyTorch can use GPU!"
    else
        echo "⚠️  PyTorch cannot use GPU - may need CUDA-enabled build"
    fi
else
    echo "ℹ️  No GPU detected - using CPU mode"
fi

# Export status for use by application
export HAS_GPU=$HAS_GPU
export CUDA_AVAILABLE=$CUDA_AVAILABLE

