# Ollama Embedding & Memory System Test Scripts

Test scripts for verifying Ollama embedding functionality and memory system integration.

## Quick Start

### Prerequisites

1. **Ollama running on localhost:11434**
   ```bash
   # If using Docker Compose
   docker-compose up -d ollama
   
   # Or run Ollama directly
   ollama serve
   ```

2. **Qdrant running on localhost:6333** (for full memory tests)
   ```bash
   # If using Docker Compose
   docker-compose up -d qdrant
   ```

3. **Environment file** (`.env` or `env` in project root)
   ```bash
   OLLAMA_URL=http://localhost:11434
   QDRANT_HOST=localhost
   QDRANT_PORT=6333
   ```

### Quick Test (Minimal)

Test just the Ollama embedding functionality:

```bash
cd agentic_system_trading
python test_ollama_quick.py
```

This test:
- ✅ Checks Ollama connection
- ✅ Tests single embedding generation
- ✅ Tests batch embedding generation

### Full Test Suite

Test the complete memory system:

```bash
cd agentic_system_trading
python test_ollama_memory.py
```

This test suite includes:
1. **Ollama Connection** - Verify Ollama is running
2. **Ollama Embedding** - Test embedding generation (single & batch)
3. **Embedding Factory** - Test factory pattern
4. **Qdrant Connection** - Verify Qdrant is running
5. **Qdrant Storage** - Test vector storage integration
6. **CAMEL Memory System** - Test full memory system with VectorDBBlock
7. **Error Handling** - Test timeout and error scenarios

## Test Scripts

### `test_ollama_quick.py`

Minimal test script that only requires Ollama to be running. Good for quick verification.

**Usage:**
```bash
python test_ollama_quick.py
```

**What it tests:**
- Ollama connection
- Single embedding generation
- Batch embedding generation

### `test_ollama_memory.py`

Comprehensive test suite for the full memory system.

**Usage:**
```bash
python test_ollama_memory.py
```

**What it tests:**
- All quick test functionality
- Embedding factory pattern
- Qdrant storage integration
- Full CAMEL memory system
- Error handling and timeouts

## Configuration

The scripts automatically:
- Load `.env` or `env` file from project root
- Override Ollama URL to use `localhost:11434`
- Override Qdrant host to use `localhost`

You can override these by setting environment variables:
```bash
export OLLAMA_URL=http://localhost:11434
export QDRANT_HOST=localhost
export QDRANT_PORT=6333
python test_ollama_memory.py
```

## Expected Output

### Successful Quick Test
```
Testing Ollama Embedding (localhost)...
✅ Ollama is running
✅ Created embedding: model=nomic-embed-text, dim=768
✅ Generated embedding: dim=768, norm=1.2345
✅ Batch embedding: 3 vectors

🎉 All quick tests passed!
```

### Successful Full Test
```
================================================================
OLLAMA EMBEDDING & MEMORY SYSTEM TEST
================================================================

Configuration:
  Ollama URL: http://localhost:11434
  Qdrant Host: localhost
  Qdrant Port: 6333

[Test results...]

================================================================
TEST SUMMARY
================================================================
  ✅ PASS: Ollama Connection
  ✅ PASS: Ollama Embedding
  ✅ PASS: Embedding Factory
  ✅ PASS: Qdrant Connection
  ✅ PASS: Qdrant Storage
  ✅ PASS: CAMEL Memory System
  ✅ PASS: Error Handling

  Total: 7/7 tests passed

🎉 All tests passed!
```

## Troubleshooting

### Ollama Connection Failed

**Error:** `Cannot connect to Ollama: Connection refused`

**Solution:**
1. Check if Ollama is running:
   ```bash
   curl http://localhost:11434/api/tags
   ```

2. Start Ollama:
   ```bash
   docker-compose up -d ollama
   # Or
   ollama serve
   ```

3. Verify the model is available:
   ```bash
   docker exec ats-ollama ollama pull nomic-embed-text
   ```

### Qdrant Connection Failed

**Error:** `Failed to connect to Qdrant`

**Solution:**
1. Check if Qdrant is running:
   ```bash
   curl http://localhost:6333/health
   ```

2. Start Qdrant:
   ```bash
   docker-compose up -d qdrant
   ```

### Timeout Errors

**Error:** `HTTP error generating embedding: timed out`

**Solution:**
- The new implementation has improved timeout handling (180s default, 3 retries)
- If timeouts persist, check:
  1. Ollama service health
  2. Model availability (`ollama list`)
  3. System resources (CPU/memory)

### Import Errors

**Error:** `ImportError: camel-ai not installed`

**Solution:**
```bash
pip install camel-ai
```

For full memory system tests, you also need:
```bash
pip install qdrant-client
```

## Features Tested

### OllamaEmbedding Improvements

The test scripts verify the improved `OllamaEmbedding` class:

- ✅ **Extended timeout** (180s default, was 30s)
- ✅ **Retry logic** (3 retries with exponential backoff)
- ✅ **Better error handling** (raises exceptions instead of silent zero vectors)
- ✅ **CAMEL-AI compatibility** (follows BaseEmbedding interface)
- ✅ **Localhost fallback** (automatic DNS error handling)

### Memory System Integration

- ✅ **VectorDBBlock** with Ollama embeddings
- ✅ **Qdrant storage** integration
- ✅ **ChatHistoryBlock** for conversation memory
- ✅ **ScoreBasedContextCreator** for context management
- ✅ **LongtermAgentMemory** full system

## Notes

- The scripts use `localhost` by default to work in both Docker and local environments
- Test collections are created with prefix `test_` and can be cleaned up manually
- The scripts are designed to be non-destructive (test collections only)
- Full memory system tests require CAMEL-AI to be installed

