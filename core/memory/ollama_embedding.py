"""
Ollama Embedding Client for lightweight embeddings.

Uses Ollama API to generate embeddings without requiring PyTorch or large models.
Follows CAMEL-AI BaseEmbedding interface pattern similar to OpenAIEmbedding.
"""
from __future__ import annotations

import os
import time
from typing import Any, List, Optional, Union
import httpx
from urllib.parse import urlparse, urlunparse
from core.settings.config import settings
from core.logging import log

try:
    from camel.embeddings.base import BaseEmbedding
    EMBEDDING_BASE_AVAILABLE = True
except ImportError:
    EMBEDDING_BASE_AVAILABLE = False

    class BaseEmbedding:
        """Minimal BaseEmbedding interface."""

        pass


class OllamaEmbedding(BaseEmbedding[str]):
    r"""Provides text embedding functionalities using Ollama's models.

    Args:
        model (str): The model name to be used for text embeddings.
            (default: :obj:`"nomic-embed-text"`)
        base_url (Optional[str]): The base URL to the Ollama service.
            (default: :obj:`None`, uses settings.ollama_url)
        timeout (int): Request timeout in seconds.
            (default: :obj:`180`, matching OpenAIEmbedding)
        max_retries (int): Maximum number of retry attempts.
            (default: :obj:`3`, matching OpenAIEmbedding)
        return_zero_on_timeout (bool): If True, return zero vector on timeout
            instead of raising exception. (default: :obj:`False`)

    Raises:
        RuntimeError: If embedding generation fails after all retries.
        ValueError: If text input is invalid.
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: Optional[str] = None,
        timeout: int = 180,  # Match OpenAIEmbedding timeout
        max_retries: int = 3,  # Match OpenAIEmbedding retries
        return_zero_on_timeout: bool = False,  # Don't return zero vectors by default
    ) -> None:
        self.model = model
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.return_zero_on_timeout = return_zero_on_timeout
        self._client: Optional[httpx.Client] = None

        # Embedding output dimension is determined dynamically from the first
        # successful response so we always respect the actual embedding shape,
        # regardless of the model (e.g. nomic-embed-text, embeddinggemma, etc.).
        # Until then, this stays None.
        self.output_dim: Optional[int] = None
        
        log.info(
            f"Initialized OllamaEmbedding with model: {model}, "
            f"URL: {self.base_url}, timeout: {timeout}s, max_retries: {max_retries}"
        )

    def _get_client(self) -> httpx.Client:
        """Get or create synchronous HTTP client with proper timeout configuration."""
        if self._client is None:
            # Use separate connect and read timeouts for better control
            timeout_config = httpx.Timeout(
                connect=10.0,  # Connection timeout
                read=self.timeout,  # Read timeout (main timeout)
                write=10.0,  # Write timeout
                pool=10.0,  # Pool timeout
            )
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=timeout_config,
                follow_redirects=True,
            )
        return self._client

    def _fallback_localhost(self) -> bool:
        """
        Swap base_url host to localhost if the current host cannot be resolved.
        Returns True if the base_url was changed.
        """
        try:
            parsed = urlparse(self.base_url)
            if parsed.hostname and "ollama" in parsed.hostname.lower() and parsed.hostname != "localhost":
                localhost = parsed._replace(netloc=f"localhost:{parsed.port or 11434}")
                new_url = urlunparse(localhost)
                log.debug(f"[OllamaEmbedding] Falling back to localhost: {new_url}")
                self.base_url = new_url
                # Reset client so next call uses the new base_url
                if self._client is not None:
                    try:
                        self._client.close()
                    except Exception:
                        pass
                    self._client = None
                return True
        except Exception:
            pass
        return False

    def _make_request(
        self,
        text: str,
        retry_count: int = 0,
        use_localhost_fallback: bool = True,
    ) -> List[float]:
        """
        Make embedding request with retry logic and exponential backoff.

        Args:
            text: Input text to embed
            retry_count: Current retry attempt number
            use_localhost_fallback: Whether to try localhost fallback on DNS errors

        Returns:
            List of floats representing the embedding vector

        Raises:
            RuntimeError: If all retries are exhausted
            ValueError: If response is invalid
        """
        client = self._get_client()

        try:
            response = client.post(
                "/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text,
                },
            )
            response.raise_for_status()
            data = response.json()
            
            if "embedding" not in data:
                raise ValueError(f"Invalid response from Ollama: {data}")
            
            embedding = data["embedding"]
            
            # Dynamically determine / validate embedding dimension
            if self.output_dim is None:
                # First successful response: lock in the true dimension
                self.output_dim = len(embedding)
                log.info(
                    "Detected Ollama embedding dimension for model '%s': %d",
                    self.model,
                    self.output_dim,
                )
            elif len(embedding) != self.output_dim:
                # If the model's dimension changes, pad/truncate but warn loudly
                log.warning(
                    "Embedding dimension mismatch for model '%s': expected %s, got %s. "
                    "Padding or truncating to match expected dimension.",
                    self.model,
                    self.output_dim,
                    len(embedding),
                )
                target_dim = self.output_dim
                if target_dim is not None:
                    if len(embedding) < target_dim:
                        embedding = embedding + [0.0] * (target_dim - len(embedding))
                    else:
                        embedding = embedding[:target_dim]
            
            return embedding

        except httpx.HTTPError as e:
            err_str = str(e).lower()
            is_timeout = "timeout" in err_str or "timed out" in err_str
            is_dns_error = (
                "name or service not known" in err_str
                or "temporary failure in name resolution" in err_str
            )

            # Try localhost fallback on DNS errors (only on first attempt)
            if is_dns_error and use_localhost_fallback and retry_count == 0:
                if self._fallback_localhost():
                    log.debug("Retrying with localhost fallback after DNS error")
                    return self._make_request(text, retry_count=0, use_localhost_fallback=False)

            # Retry with exponential backoff
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff: 1s, 2s, 4s
                log.warning(
                    f"HTTP error generating embedding (attempt {retry_count + 1}/{self.max_retries + 1}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                return self._make_request(text, retry_count=retry_count + 1, use_localhost_fallback=False)

            # All retries exhausted
            if is_timeout and self.return_zero_on_timeout:
                dim = self.output_dim or 768
                log.warning(
                    f"Ollama embedding timeout after {self.max_retries + 1} attempts, "
                    f"returning zero vector of dimension {dim}"
                )
                return [0.0] * dim

            # Raise exception if not returning zero vector
            raise RuntimeError(
                f"Failed to generate embedding after {self.max_retries + 1} attempts: {e}"
            ) from e

        except Exception as e:
            # For non-HTTP errors, don't retry
            log.error(f"Unexpected error generating embedding: {e}")
            raise

    def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector

        Raises:
            ValueError: If text is empty or invalid
            RuntimeError: If embedding generation fails after all retries
        """
        # Validate input text
        if not text or not isinstance(text, str):
            raise ValueError(f"Invalid text input for embedding: {text}")

        # Clean and validate text content
        import re
        cleaned_text = text.strip()
        # Remove control characters
        cleaned_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned_text)

        # Ensure minimum content length
        if not cleaned_text or len(cleaned_text) < 1:
            if self.return_zero_on_timeout:
                dim = self.output_dim or 768
                log.warning(
                    "Empty or invalid text provided to embedding, "
                    "returning zero vector of dimension %d",
                    dim,
                )
                return [0.0] * dim
            raise ValueError("Text input is empty or contains only control characters")

        try:
            embedding = self._make_request(cleaned_text)
            log.debug(
                f"Generated embedding of dimension {len(embedding)} for text: {cleaned_text[:50]}..."
            )
            return embedding
        except Exception as e:
            log.error(f"Error generating embedding: {e}")
            raise

    def embed_list(
        self,
        objs: list[str],
        **kwargs: Any,
    ) -> list[list[float]]:
        r"""Generates embeddings for the given texts.

        This method is required by CAMEL's BaseEmbedding interface.

        Args:
            objs (list[str]): The texts for which to generate the embeddings.
            **kwargs (Any): Extra kwargs (currently unused, for compatibility).

        Returns:
            list[list[float]]: A list that represents the generated embeddings
                as lists of floating-point numbers.
        """
        if not objs:
            return []

        # If dimension is still unknown, try to infer it once up-front so that
        # any zero-vector fallbacks have the correct shape.
        if self.output_dim is None:
            try:
                _ = self.embed("dimension probe for embed_list()")
            except Exception:
                # If this fails, we'll fall back to a reasonable default later.
                log.warning(
                    "Could not infer embedding dimension before batch; "
                    "will fall back to default if needed."
                )

        embeddings = []
        for text in objs:
            try:
                embedding = self.embed(text)
                embeddings.append(embedding)
            except Exception as e:
                # On error, either return zero vector or re-raise based on configuration
                if self.return_zero_on_timeout:
                    dim = self.output_dim or 768
                    log.warning(
                        f"Error embedding text '{text[:50]}...': {e}. "
                        f"Returning zero vector with dimension {dim}."
                    )
                    embeddings.append([0.0] * dim)
                else:
                    # Re-raise to maintain error visibility
                    log.error(f"Error embedding text '{text[:50]}...': {e}")
                    raise

        return embeddings

    def get_output_dim(self) -> int:
        r"""Returns the output dimension of the embeddings.

        Returns:
            int: The dimensionality of the embedding for the current model.
        """
        if self.output_dim is not None:
            return self.output_dim

        # Dimension not yet known: probe with a tiny request to respect
        # the actual embedding shape served by the Ollama model.
        try:
            embedding = self._make_request("dimension probe")
            self.output_dim = len(embedding)
            log.info(
                "Determined embedding output_dim via probe for model '%s': %d",
                self.model,
                self.output_dim,
            )
            return self.output_dim
        except Exception as e:
            log.error(
                "Failed to determine embedding dimension for model '%s': %s. "
                "Falling back to default 768.",
                self.model,
                e,
            )
            # Fallback to a safe default; this still keeps CAMEL & Qdrant consistent
            # but may not match the true model dimension in rare failure cases.
            self.output_dim = 768
            return self.output_dim

    # Async methods for compatibility (if needed in future)
    async def embed_async(self, text: str) -> List[float]:
        """Async wrapper around the synchronous embed for compatibility."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed, text)

    async def embed_batch_async(self, texts: List[str]) -> List[List[float]]:
        """Async wrapper to generate embeddings concurrently when needed."""
        import asyncio
        loop = asyncio.get_running_loop()
        tasks = [loop.run_in_executor(None, self.embed, text) for text in texts]
        return await asyncio.gather(*tasks)

    def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()
