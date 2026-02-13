"""
CAMEL Memory Manager

Wraps CAMEL's LongtermAgentMemory with Qdrant storage and Redis chat history.
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any
from core.settings.config import settings
from core.logging import log
from core.memory.qdrant_storage import QdrantStorageFactory
from core.memory.embedding_config import EmbeddingFactory

try:
    from camel.memories import (
        LongtermAgentMemory,
        ChatHistoryBlock,
        VectorDBBlock,
        MemoryRecord,
        ScoreBasedContextCreator,
    )
    from camel.messages import BaseMessage
    from camel.types import ModelType, OpenAIBackendRole
    from camel.utils import OpenAITokenCounter
    from camel.storages import InMemoryKeyValueStorage
    CAMEL_MEMORY_AVAILABLE = True
except ImportError:
    CAMEL_MEMORY_AVAILABLE = False
    log.warning("CAMEL memory not available. Install with: pip install camel-ai")


class CamelMemoryManager:
    """Manager for CAMEL long-term agent memory."""
    
    def __init__(
        self,
        agent_id: str,
        collection_name: Optional[str] = None,
        model_type: Optional["ModelType"] = None  # String annotation for forward reference
    ):
        """
        Initialize CAMEL memory manager.
        
        Args:
            agent_id: Unique identifier for the agent
            collection_name: Qdrant collection name (defaults to settings)
            model_type: Model type for token counting (defaults to GPT_4O_MINI)
        """
        if not CAMEL_MEMORY_AVAILABLE:
            raise ImportError("CAMEL memory not installed")
        
        self.agent_id = agent_id
        self.collection_name = collection_name or f"{settings.qdrant_collection_name}_{agent_id}"
        self.model_type = model_type or ModelType.GPT_4O_MINI
        
        # Initialize components
        self._memory: Optional[LongtermAgentMemory] = None
        self._initialize_memory()
    
    def _initialize_memory(self):
        """Initialize the CAMEL memory system."""
        try:
            # Get embedding model and dimension
            embedding = EmbeddingFactory.create_embedding()
            vector_dim = EmbeddingFactory.get_output_dim()
            
            # Ensure Qdrant collection exists
            QdrantStorageFactory.ensure_collection_exists(
                collection_name=self.collection_name,
                vector_dim=vector_dim
            )
            
            # Create Qdrant storage
            qdrant_storage = QdrantStorageFactory.create_storage(
                collection_name=self.collection_name,
                vector_dim=vector_dim
            )
            
            # Create chat history block (using Redis-compatible in-memory for now)
            # In production, this could be backed by Redis
            chat_history_block = ChatHistoryBlock(
                storage=InMemoryKeyValueStorage(),
                keep_rate=0.9
            )
            
            # Create vector DB block
            # Note: retrieve_limit is set on LongtermAgentMemory, not VectorDBBlock
            vector_db_block = VectorDBBlock(
                storage=qdrant_storage,
                embedding=embedding
            )
            
            # Create context creator
            context_creator = ScoreBasedContextCreator(
                token_counter=OpenAITokenCounter(self.model_type),
                token_limit=settings.memory_token_limit
            )
            
            # Create long-term memory
            self._memory = LongtermAgentMemory(
                context_creator=context_creator,
                chat_history_block=chat_history_block,
                vector_db_block=vector_db_block,
                retrieve_limit=settings.memory_retrieve_limit
            )
            
            log.info(f"Initialized CAMEL memory for agent: {self.agent_id}")
            
        except Exception as e:
            log.error(f"Failed to initialize CAMEL memory: {e}")
            raise
    
    @property
    def memory(self) -> LongtermAgentMemory:
        """Get the memory instance."""
        if self._memory is None:
            raise RuntimeError("Memory not initialized")
        return self._memory
    
    def write_record(
        self,
        message: BaseMessage,
        role: Optional[OpenAIBackendRole] = None,
        extra_info: Optional[Dict[str, Any]] = None
    ):
        """
        Write a single memory record.
        
        Args:
            message: The message to store
            role: Backend role (USER or ASSISTANT). If None, inferred from message role.
            extra_info: Optional metadata
        """
        if role is None:
            # Infer role from message role name
            if hasattr(message, 'role_name'):
                if message.role_name.lower() in ['user', 'task coordinator']:
                    role = OpenAIBackendRole.USER
                else:
                    role = OpenAIBackendRole.ASSISTANT
            else:
                role = OpenAIBackendRole.USER
        
        # ✅ Validate message content before storing (prevent empty vector errors)
        message_content = getattr(message, 'content', '') or ''
        if not message_content or len(message_content.strip()) == 0:
            log.warning(f"Skipping memory write for empty message (role: {role}, agent_id: {self.agent_id})")
            return  # Skip storing empty messages to prevent vector dimension errors
        
        # ✅ Additional validation: ensure content is not just whitespace or special chars
        if not message_content.strip() or len(message_content.strip()) < 3:
            log.warning(f"Skipping memory write for message with insufficient content (length: {len(message_content)}, agent_id: {self.agent_id})")
            return
        
        try:
            # ✅ Additional validation: ensure content can be embedded (not just special chars)
            # Remove any control characters that might cause embedding issues
            import re
            cleaned_content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', message_content)
            
            # ✅ Ensure minimum content length for valid embeddings
            # CAMEL embeddings require meaningful content to generate proper vectors
            min_content_length = 3
            if not cleaned_content or len(cleaned_content.strip()) < min_content_length:
                log.warning(
                    f"Skipping memory write for message with insufficient content "
                    f"(length: {len(cleaned_content) if cleaned_content else 0}, "
                    f"min: {min_content_length}, agent_id: {self.agent_id})"
                )
                return
            
            # ✅ Validate that message has valid content attribute before creating record
            # This prevents shape errors when CAMEL tries to embed empty messages
            if not hasattr(message, 'content') or not message.content:
                log.warning(f"Skipping memory write: message has no content attribute (agent_id: {self.agent_id})")
                return
            
            record = MemoryRecord(
                message=message,
                role_at_backend=role,
                extra_info=extra_info or {}
            )
            
            # ✅ Write with error handling for vector dimension issues
            try:
                self.memory.write_records([record])
            except (ValueError, TypeError) as embed_error:
                # Check if it's a shape/dimension error
                error_str = str(embed_error).lower()
                if "shape" in error_str or "dimension" in error_str or "broadcast" in error_str or "aligned" in error_str:
                    log.warning(
                        f"Vector dimension/shape error when storing memory record: {embed_error}. "
                        f"Message content: '{message_content[:100]}...' (length: {len(message_content)}). "
                        f"Agent: {self.agent_id}. Skipping record."
                    )
                    return  # Skip this record to prevent shape mismatches
                raise  # Re-raise if it's a different error
        except ValueError as e:
            # ✅ Handle vector dimension errors gracefully
            if "could not broadcast" in str(e) or "shape" in str(e) or "broadcast" in str(e).lower():
                log.warning(f"Vector dimension error when storing memory record: {e}. Message content length: {len(message_content)}, agent_id: {self.agent_id}")
                # Skip this record - likely empty or invalid content
                return
            else:
                raise
        except Exception as e:
            log.error(f"Failed to write memory record: {e}", exc_info=True)
    
    def write_records(
        self,
        records: List[MemoryRecord]
    ):
        """Write multiple memory records with error handling."""
        # ✅ Filter out empty messages before storing to prevent vector dimension errors
        valid_records = []
        for record in records:
            try:
                message = getattr(record, 'message', None)
                if message:
                    message_content = getattr(message, 'content', '') or ''
                    if message_content and len(message_content.strip()) > 0:
                        valid_records.append(record)
                    else:
                        log.debug(f"Skipping empty message record for memory storage")
                else:
                    log.warning(f"MemoryRecord has no message attribute, skipping")
            except Exception as e:
                log.warning(f"Error validating memory record: {e}, skipping")
                continue
        
        if not valid_records:
            log.debug("No valid records to store in memory")
            return
        
        try:
            self.memory.write_records(valid_records)
        except (ValueError, TypeError) as e:
            # ✅ Handle vector dimension errors gracefully
            error_str = str(e)
            if "could not broadcast" in error_str or "shape" in error_str:
                log.warning(f"Vector dimension error when storing memory records: {e}. Skipping storage.")
                # Don't re-raise - this is a known issue with empty vectors in CAMEL
                return
            else:
                # Re-raise other errors
                raise
        except Exception as e:
            # ✅ Log but don't fail on memory storage errors
            log.warning(f"Error storing memory records (non-critical): {e}")
            # Don't re-raise - memory storage failures shouldn't break the pipeline
    
    def get_context(self) -> tuple[List[BaseMessage], int]:
        """
        Get context from memory.
        
        Returns:
            Tuple of (messages, token_count)
        """
        return self.memory.get_context()
    
    def retrieve(self, query: str) -> List:
        """
        Retrieve relevant records from memory.
        
        Args:
            query: Query string for semantic search
            
        Returns:
            List of ContextRecord objects
        """
        return self.memory.retrieve(query)
    
    def clear(self):
        """Clear all memory."""
        self.memory.clear()
        log.info(f"Cleared memory for agent: {self.agent_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        try:
            # Get context to see current state
            context, token_count = self.get_context()
            
            return {
                "agent_id": self.agent_id,
                "collection_name": self.collection_name,
                "context_message_count": len(context),
                "context_token_count": token_count,
                "retrieve_limit": settings.memory_retrieve_limit,
            }
        except Exception as e:
            log.error(f"Failed to get memory stats: {e}")
            return {
                "agent_id": self.agent_id,
                "error": str(e)
            }

