"""
Neo4j Memory Toolkit for CAMEL Agents.

Provides CAMEL-compatible tools for interacting with Neo4j knowledge graph memory.
Wraps Neo4jMemory operations for use in CAMEL agents.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import sys
import os
from pathlib import Path

# Add mcp-neo4j-memory to path if needed
# Try multiple possible paths
possible_paths = [
    os.path.join(os.path.dirname(__file__), "../../../mcp-neo4j-memory/src"),
    os.path.join(os.path.dirname(__file__), "../../../../mcp-neo4j-memory/src"),
    os.path.join(Path(__file__).resolve().parents[3], "mcp-neo4j-memory", "src"),
]

for neo4j_memory_path in possible_paths:
    abs_path = os.path.abspath(neo4j_memory_path)
    if os.path.exists(abs_path) and abs_path not in sys.path:
        sys.path.insert(0, abs_path)
        break

try:
    from camel.toolkits.base import BaseToolkit
    from camel.toolkits.function_tool import FunctionTool
    from camel.logger import get_logger
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:
    BaseToolkit = object  # type: ignore
    FunctionTool = None
    CAMEL_TOOLS_AVAILABLE = False

try:
    from neo4j import AsyncGraphDatabase
    from mcp_neo4j_memory.neo4j_memory import (
        Neo4jMemory,
        Entity,
        Relation,
        ObservationAddition,
        ObservationDeletion,
        KnowledgeGraph
    )
    NEO4J_AVAILABLE = True
except ImportError as e:
    NEO4J_AVAILABLE = False
    Neo4jMemory = None  # type: ignore

from core.settings.config import settings
from core.logging import log

logger = get_logger(__name__)


class Neo4jMemoryToolkit(BaseToolkit):
    r"""A toolkit for interacting with Neo4j knowledge graph memory.
    
    This toolkit allows agents to:
    - Read and search knowledge graphs
    - Create entities and relationships
    - Add observations to entities
    - Delete entities and observations (for pruning)
    """

    def __init__(self, timeout: Optional[float] = None):
        r"""Initializes the Neo4jMemoryToolkit and sets up the Neo4j driver.
        
        Args:
            timeout: Optional timeout for requests
        """
        super().__init__(timeout=timeout)
        self._memory: Optional[Neo4jMemory] = None
        self._driver = None

    async def initialize(self) -> None:
        """Initialize the Neo4j driver and memory instance."""
        if not NEO4J_AVAILABLE:
            logger.warning("Neo4j dependencies not available")
            return
        
        try:
            neo4j_uri = getattr(settings, 'neo4j_uri', 'bolt://localhost:7687')
            neo4j_user = getattr(settings, 'neo4j_user', 'neo4j')
            neo4j_password = getattr(settings, 'neo4j_password', 'password')
            neo4j_database = getattr(settings, 'neo4j_database', 'neo4j')
            
            self._driver = AsyncGraphDatabase.driver(
                neo4j_uri,
                auth=(neo4j_user, neo4j_password),
                database=neo4j_database
            )
            
            # Verify connection
            await self._driver.verify_connectivity()
            
            self._memory = Neo4jMemory(self._driver)
            
            # Create fulltext index
            await self._memory.create_fulltext_index()
            
            logger.info("Neo4j Memory Toolkit initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Neo4j Memory Toolkit: {e}")
            self._memory = None

    async def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver:
            try:
                await self._driver.close()
            except Exception as e:
                logger.debug(f"Error closing Neo4j driver: {e}")
    
    async def _create_memory_in_loop(self) -> tuple[Optional[Neo4jMemory], Optional[Any]]:
        """Create a Neo4jMemory instance and driver in the current event loop.
        
        Each operation creates its own driver connection to avoid event loop conflicts.
        Returns (memory, driver) tuple so driver can be closed after operation.
        """
        if not NEO4J_AVAILABLE:
            return None, None
        
        try:
            neo4j_uri = getattr(settings, 'neo4j_uri', 'bolt://localhost:7687')
            neo4j_user = getattr(settings, 'neo4j_user', 'neo4j')
            neo4j_password = getattr(settings, 'neo4j_password', 'password')
            neo4j_database = getattr(settings, 'neo4j_database', 'neo4j')
            
            driver = AsyncGraphDatabase.driver(
                neo4j_uri,
                auth=(neo4j_user, neo4j_password),
                database=neo4j_database
            )
            await driver.verify_connectivity()
            memory = Neo4jMemory(driver)
            await memory.create_fulltext_index()
            return memory, driver
        except Exception as e:
            logger.error(f"Failed to create Neo4j connection: {e}")
            return None, None

    def read_graph(self) -> Dict[str, Any]:
        """Read the entire knowledge graph with all entities and relationships."""
        from core.camel_tools.async_wrapper import wrap_async_tool
        
        async def _async_read():
            """Async function that creates driver in current loop and reads graph."""
            # Create driver connection in the current event loop
            neo4j_uri = getattr(settings, 'neo4j_uri', 'bolt://localhost:7687')
            neo4j_user = getattr(settings, 'neo4j_user', 'neo4j')
            neo4j_password = getattr(settings, 'neo4j_password', 'password')
            neo4j_database = getattr(settings, 'neo4j_database', 'neo4j')
            
            driver = AsyncGraphDatabase.driver(
                neo4j_uri,
                auth=(neo4j_user, neo4j_password),
                database=neo4j_database
            )
            try:
                await driver.verify_connectivity()
                memory = Neo4jMemory(driver)
                await memory.create_fulltext_index()
                
                result = await memory.read_graph()
                return {
                    "success": True,
                    "entities": [e.model_dump() for e in result.entities],
                    "relations": [r.model_dump() for r in result.relations]
                }
            except Exception as e:
                logger.error(f"Error reading graph: {e}")
                return {"success": False, "error": str(e)}
            finally:
                await driver.close()
        
        # Wrap the async function to handle event loop properly
        sync_read = wrap_async_tool(_async_read)
        return sync_read()

    def create_entities(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create multiple new entities in the knowledge graph."""
        from core.camel_tools.async_wrapper import wrap_async_tool
        
        async def _async_create():
            """Async function that creates driver in current loop and creates entities."""
            memory, driver = await self._create_memory_in_loop()
            if not memory:
                return {"success": False, "error": "Neo4j memory not available"}
            try:
                entity_objects = [Entity(**e) for e in entities]
                result = await memory.create_entities(entity_objects)
                return {
                    "success": True,
                    "entities": [e.model_dump() for e in result]
                }
            except Exception as e:
                logger.error(f"Error creating entities: {e}")
                return {"success": False, "error": str(e)}
            finally:
                if driver:
                    await driver.close()
        
        sync_create = wrap_async_tool(_async_create)
        return sync_create()

    def create_relations(self, relations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create multiple new relationships between existing entities."""
        from core.camel_tools.async_wrapper import wrap_async_tool
        
        async def _async_create():
            """Async function that creates driver in current loop and creates relations."""
            memory, driver = await self._create_memory_in_loop()
            if not memory:
                return {"success": False, "error": "Neo4j memory not available"}
            try:
                relation_objects = [Relation(**r) for r in relations]
                result = await memory.create_relations(relation_objects)
                return {
                    "success": True,
                    "relations": [r.model_dump() for r in result]
                }
            except Exception as e:
                logger.error(f"Error creating relations: {e}")
                return {"success": False, "error": str(e)}
            finally:
                if driver:
                    await driver.close()
        
        sync_create = wrap_async_tool(_async_create)
        return sync_create()

    def add_observations(self, observations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add new observations to existing entities."""
        from core.camel_tools.async_wrapper import wrap_async_tool
        
        async def _async_add():
            """Async function that creates driver in current loop and adds observations."""
            memory, driver = await self._create_memory_in_loop()
            if not memory:
                return {"success": False, "error": "Neo4j memory not available"}
            try:
                obs_objects = [ObservationAddition(**o) for o in observations]
                result = await memory.add_observations(obs_objects)
                return {
                    "success": True,
                    "results": result
                }
            except Exception as e:
                logger.error(f"Error adding observations: {e}")
                return {"success": False, "error": str(e)}
            finally:
                if driver:
                    await driver.close()
        
        sync_add = wrap_async_tool(_async_add)
        return sync_add()

    def search_memories(self, query: str) -> Dict[str, Any]:
        """Search for entities in the knowledge graph using fulltext search."""
        from core.camel_tools.async_wrapper import wrap_async_tool
        
        async def _async_search():
            """Async function that creates driver in current loop and searches memories."""
            memory, driver = await self._create_memory_in_loop()
            if not memory:
                return {"success": False, "error": "Neo4j memory not available"}
            try:
                result = await memory.search_memories(query)
                return {
                    "success": True,
                    "entities": [e.model_dump() for e in result.entities],
                    "relations": [r.model_dump() for r in result.relations]
                }
            except Exception as e:
                logger.error(f"Error searching memories: {e}")
                return {"success": False, "error": str(e)}
            finally:
                if driver:
                    await driver.close()
        
        sync_search = wrap_async_tool(_async_search)
        return sync_search()

    def find_memories_by_name(self, names: List[str]) -> Dict[str, Any]:
        """Find specific entities by their exact names."""
        from core.camel_tools.async_wrapper import wrap_async_tool
        
        async def _async_find():
            """Async function that creates driver in current loop and finds memories by name."""
            memory, driver = await self._create_memory_in_loop()
            if not memory:
                return {"success": False, "error": "Neo4j memory not available"}
            try:
                result = await memory.find_memories_by_name(names)
                return {
                    "success": True,
                    "entities": [e.model_dump() for e in result.entities],
                    "relations": [r.model_dump() for r in result.relations]
                }
            except Exception as e:
                logger.error(f"Error finding memories by name: {e}")
                return {"success": False, "error": str(e)}
            finally:
                if driver:
                    await driver.close()
        
        sync_find = wrap_async_tool(_async_find)
        return sync_find()

    def delete_entities(self, entity_names: List[str]) -> Dict[str, Any]:
        """Delete entities and all their associated relationships."""
        from core.camel_tools.async_wrapper import wrap_async_tool
        
        async def _async_delete():
            """Async function that creates driver in current loop and deletes entities."""
            memory, driver = await self._create_memory_in_loop()
            if not memory:
                return {"success": False, "error": "Neo4j memory not available"}
            try:
                await memory.delete_entities(entity_names)
                return {
                    "success": True,
                    "deleted_count": len(entity_names)
                }
            except Exception as e:
                logger.error(f"Error deleting entities: {e}")
                return {"success": False, "error": str(e)}
            finally:
                if driver:
                    await driver.close()
        
        sync_delete = wrap_async_tool(_async_delete)
        return sync_delete()

    def delete_observations(self, deletions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Delete specific observations from entities."""
        from core.camel_tools.async_wrapper import wrap_async_tool
        
        async def _async_delete():
            """Async function that creates driver in current loop and deletes observations."""
            memory, driver = await self._create_memory_in_loop()
            if not memory:
                return {"success": False, "error": "Neo4j memory not available"}
            try:
                deletion_objects = [ObservationDeletion(**d) for d in deletions]
                await memory.delete_observations(deletion_objects)
                return {
                    "success": True,
                    "deleted_count": len(deletions)
                }
            except Exception as e:
                logger.error(f"Error deleting observations: {e}")
                return {"success": False, "error": str(e)}
            finally:
                if driver:
                    await driver.close()
        
        sync_delete = wrap_async_tool(_async_delete)
        return sync_delete()

    def get_tools(self) -> List[FunctionTool]:
        """Returns a list of FunctionTool objects for Neo4j memory operations."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            logger.warning("CAMEL tools not available, returning empty list")
            return []
        
        if not NEO4J_AVAILABLE:
            logger.warning("Neo4j dependencies not available, returning empty list")
            return []
        
        toolkit_instance = self
        
        # Read graph tool
        def read_graph() -> Dict[str, Any]:
            """Read the entire knowledge graph with all entities and relationships.
            
            Returns the complete memory graph including all stored entities and their relationships.
            Use this to get a full overview of stored knowledge.
            """
            return toolkit_instance.read_graph()
        
        read_graph.__name__ = "read_graph"
        from core.camel_tools.async_wrapper import create_function_tool
        
        # Provide explicit schema following OpenAI format
        schema_read = {
            "type": "function",
            "function": {
                "name": "read_graph",
                "description": "Read the entire knowledge graph with all entities and relationships. Returns the complete memory graph including all stored entities and their relationships. Use this to get a full overview of stored knowledge.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        read_graph_tool = create_function_tool(read_graph, explicit_schema=schema_read)
        
        # Create entities tool
        def create_entities(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
            """Create multiple new entities in the knowledge graph.
            
            Args:
                entities: List of entity dictionaries with 'name', 'type', and 'observations' fields.
                         Example: [{"name": "BTC", "type": "asset", "observations": ["Bitcoin cryptocurrency"]}]
            """
            return toolkit_instance.create_entities(entities)
        
        create_entities.__name__ = "create_entities"
        
        # Provide explicit schema to avoid Pydantic model generation issues
        schema_create_entities = {
            "type": "function",
            "function": {
                "name": "create_entities",
                "description": "Create multiple new entities in the knowledge graph. Creates new memory entities with their associated observations. If an entity with the same name already exists, this operation will merge the observations with existing ones.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Unique entity name (e.g., 'BTC', 'ETH', 'crypto_market')"},
                                    "type": {"type": "string", "description": "Entity type/category (e.g., 'asset', 'market', 'concept')"},
                                    "observations": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "List of observations/facts"
                                    }
                                },
                                "required": ["name", "type", "observations"],
                                "additionalProperties": False
                            },
                            "description": "List of entities to create"
                        }
                    },
                    "required": ["entities"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        create_entities_tool = create_function_tool(create_entities, explicit_schema=schema_create_entities)
        
        # Create relations tool
        def create_relations(relations: List[Dict[str, Any]]) -> Dict[str, Any]:
            """Create multiple new relationships between existing entities.
            
            Args:
                relations: List of relation dictionaries with 'source', 'target', and 'relationType' fields.
                          Example: [{"source": "BTC", "target": "crypto_market", "relationType": "TRADED_IN"}]
            """
            return toolkit_instance.create_relations(relations)
        
        create_relations.__name__ = "create_relations"
        
        # Provide explicit schema to avoid Pydantic model generation issues
        schema_create_relations = {
            "type": "function",
            "function": {
                "name": "create_relations",
                "description": "Create multiple new relationships between existing entities. Creates directed relationships between entities that already exist. Both source and target entities must already be present in the graph. Use descriptive relationship types.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "relations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source": {"type": "string", "description": "Source entity name (must match existing entity)"},
                                    "target": {"type": "string", "description": "Target entity name (must match existing entity)"},
                                    "relationType": {"type": "string", "description": "Relationship type (e.g., 'TRADED_IN', 'RELATED_TO', 'AFFECTS')"}
                                },
                                "required": ["source", "target", "relationType"],
                                "additionalProperties": False
                            },
                            "description": "List of relationships to create"
                        }
                    },
                    "required": ["relations"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        create_relations_tool = create_function_tool(create_relations, explicit_schema=schema_create_relations)
        
        # Add observations tool
        def add_observations(observations: List[Dict[str, Any]]) -> Dict[str, Any]:
            """Add new observations to existing entities.
            
            Args:
                observations: List of observation dictionaries with 'entityName' and 'observations' fields.
                             Example: [{"entityName": "BTC", "observations": ["Price increased 5% today"]}]
            """
            return toolkit_instance.add_observations(observations)
        
        add_observations.__name__ = "add_observations"
        
        # Provide explicit schema to avoid Pydantic model generation issues
        schema_add_obs = {
            "type": "function",
            "function": {
                "name": "add_observations",
                "description": "Add new observations/facts to existing entities in the knowledge graph. Appends new observations to entities that already exist. The entity must be present in the graph before adding observations. Each observation should be a distinct fact.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "observations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "entityName": {"type": "string", "description": "Exact name of existing entity"},
                                    "observations": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "New observations/facts to add"
                                    }
                                },
                                "required": ["entityName", "observations"],
                                "additionalProperties": False
                            },
                            "description": "List of observations to add"
                        }
                    },
                    "required": ["observations"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        add_observations_tool = create_function_tool(add_observations, explicit_schema=schema_add_obs)
        
        # Search memories tool
        def search_memories(query: str) -> Dict[str, Any]:
            """Search for entities in the knowledge graph using fulltext search.
            
            Args:
                query: Search query string (e.g., "bitcoin price" or "market sentiment")
            """
            return toolkit_instance.search_memories(query)
        
        search_memories.__name__ = "search_memories"
        
        # Provide explicit schema following OpenAI format
        schema_search = {
            "type": "function",
            "function": {
                "name": "search_memories",
                "description": "Search for entities in the knowledge graph using fulltext search. Searches across entity names, types, and observations using Neo4j's fulltext index. Returns matching entities and their related connections. Supports partial matches and multiple search terms.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Fulltext search query to find entities by name, type, or observations (e.g., 'bitcoin price', 'market sentiment', 'BTC ETH')"
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        search_memories_tool = create_function_tool(search_memories, explicit_schema=schema_search)
        
        # Find memories by name tool
        def find_memories_by_name(names: List[str]) -> Dict[str, Any]:
            """Find specific entities by their exact names.
            
            Args:
                names: List of exact entity names to find (e.g., ["BTC", "ETH", "SOL"])
            """
            return toolkit_instance.find_memories_by_name(names)
        
        find_memories_by_name.__name__ = "find_memories_by_name"
        
        # Provide explicit schema to avoid Pydantic model generation issues
        schema_find = {
            "type": "function",
            "function": {
                "name": "find_memories_by_name",
                "description": "Find specific entities by their exact names. Retrieves entities that exactly match the provided names, along with all their relationships and connected entities. Use this when you know the exact entity names.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of exact entity names to retrieve (e.g., ['BTC', 'ETH', 'SOL'])"
                        }
                    },
                    "required": ["names"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        find_memories_by_name_tool = create_function_tool(find_memories_by_name, explicit_schema=schema_find)
        
        # Delete entities tool
        def delete_entities(entity_names: List[str]) -> Dict[str, Any]:
            """Delete entities and all their associated relationships.
            
            Args:
                entity_names: List of exact entity names to delete (e.g., ["OldEntity"])
            """
            return toolkit_instance.delete_entities(entity_names)
        
        delete_entities.__name__ = "delete_entities"
        
        # Provide explicit schema to avoid Pydantic model generation issues
        schema_delete_entities = {
            "type": "function",
            "function": {
                "name": "delete_entities",
                "description": "Delete entities and all their associated relationships from the knowledge graph. Permanently removes entities from the graph along with all relationships they participate in. This is a destructive operation that cannot be undone. Entity names must match exactly.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of exact entity names to delete permanently (e.g., ['OldEntity', 'OutdatedData'])"
                        }
                    },
                    "required": ["entity_names"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        delete_entities_tool = create_function_tool(delete_entities, explicit_schema=schema_delete_entities)
        
        # Delete observations tool
        def delete_observations(deletions: List[Dict[str, Any]]) -> Dict[str, Any]:
            """Delete specific observations from entities.
            
            Args:
                deletions: List of deletion dictionaries with 'entityName' and 'observations' fields.
                          Example: [{"entityName": "BTC", "observations": ["Outdated observation"]}]
            """
            return toolkit_instance.delete_observations(deletions)
        
        delete_observations.__name__ = "delete_observations"
        
        # Provide explicit schema to avoid Pydantic model generation issues
        schema_delete_obs = {
            "type": "function",
            "function": {
                "name": "delete_observations",
                "description": "Delete specific observations from existing entities in the knowledge graph. Removes specific observation texts from entities. The observation text must match exactly what is stored. The entity will remain but the specified observations will be deleted.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "deletions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "entityName": {"type": "string", "description": "Exact name of existing entity"},
                                    "observations": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Exact observation texts to delete"
                                    }
                                },
                                "required": ["entityName", "observations"],
                                "additionalProperties": False
                            },
                            "description": "List of specific observations to remove"
                        }
                    },
                    "required": ["deletions"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        delete_observations_tool = create_function_tool(delete_observations, explicit_schema=schema_delete_obs)
        
        return [
            read_graph_tool,
            create_entities_tool,
            create_relations_tool,
            add_observations_tool,
            search_memories_tool,
            find_memories_by_name_tool,
            delete_entities_tool,
            delete_observations_tool,
        ]

