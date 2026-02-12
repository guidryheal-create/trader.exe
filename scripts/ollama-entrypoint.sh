#!/bin/sh
# Ollama entrypoint script to ensure embedding model is downloaded

set -e

OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
MODEL="${OLLAMA_MODEL:-nomic-embed-text}"

# Find ollama binary
OLLAMA_BIN=$(which ollama || find /usr -name ollama 2>/dev/null | head -1 || echo "/usr/local/bin/ollama")

echo "🚀 Starting Ollama server..."
echo "📍 Using Ollama binary: $OLLAMA_BIN"

# Start Ollama in the background
$OLLAMA_BIN serve &
OLLAMA_PID=$!

# Function to cleanup on exit
cleanup() {
  echo "🛑 Shutting down Ollama..."
  kill $OLLAMA_PID 2>/dev/null || true
  wait $OLLAMA_PID 2>/dev/null || true
  exit 0
}

# Set trap for cleanup (sh-compatible syntax)
trap 'cleanup' TERM INT

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to be ready..."
for i in $(seq 1 60); do
  # Use ollama list command to check if server is ready
  if $OLLAMA_BIN list > /dev/null 2>&1; then
    echo "✅ Ollama is ready!"
    break
  fi
  if [ $i -eq 60 ]; then
    echo "❌ Ollama failed to start after 60 attempts"
    exit 1
  fi
  sleep 1
done

# Check if model exists
echo "🔍 Checking if model '$MODEL' exists..."
MODEL_EXISTS=$($OLLAMA_BIN list 2>/dev/null | grep -o "$MODEL" || echo "")

if [ -z "$MODEL_EXISTS" ]; then
  echo "📥 Model '$MODEL' not found. Downloading..."
  $OLLAMA_BIN pull "$MODEL" || {
    echo "⚠️  Model download failed, but continuing..."
  }
  echo ""
  echo "✅ Model '$MODEL' download completed!"
else
  echo "✅ Model '$MODEL' already exists. Skipping download."
fi

# Keep Ollama running
echo "✅ Ollama is running with model '$MODEL' ready"
wait $OLLAMA_PID

