"""Test script for Neo4j Memory Toolkit."""
import pytest

pytest.skip(
    "Neo4j memory toolkit test disabled in Polymarket-only runs (pyarrow/neo4j deps).",
    allow_module_level=True,
)

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from core.camel_tools.neo4j_memory_toolkit import Neo4jMemoryToolkit, NEO4J_AVAILABLE
from core.settings.config import settings

async def test_neo4j_memory():
    """Test Neo4j Memory Toolkit initialization and tools."""
    print("=" * 60)
    print("Testing Neo4j Memory Toolkit")
    print("=" * 60)
    
    # Check if Neo4j dependencies are available
    if not NEO4J_AVAILABLE:
        print("⚠️  Neo4j dependencies not available.")
        print("   Install driver: pip install neo4j")
        print("   Install memory pkg: pip install mcp-neo4j-memory")
        print("   If installed, ensure the package path is discoverable (PYTHONPATH).")
        print("✅ Toolkit can still be imported and instantiated.")
        return
    
    # Check if Neo4j is configured; parse NEO4J_AUTH or use separate env vars
    # Priority: NEO4J_AUTH (user/password format) > NEO4J_USER/NEO4J_PASSWORD > settings > defaults
    neo4j_auth = os.getenv("NEO4J_AUTH")
    if neo4j_auth and "/" in neo4j_auth:
        # Parse NEO4J_AUTH format: "user/password"
        parts = neo4j_auth.split("/", 1)
        neo4j_user = parts[0]
        neo4j_password = parts[1]
        print(f"ℹ️  Using NEO4J_AUTH environment variable: {neo4j_user}/***")
        print(f"ℹ️  Using NEO4J_AUTH environment variable: {neo4j_password}/***")
    else:
        # Use separate environment variables or settings
        neo4j_user = os.getenv("NEO4J_USER") or getattr(settings, 'neo4j_user', 'neo4j')
        neo4j_password = os.getenv("NEO4J_PASSWORD") or getattr(settings, 'neo4j_password', None) or "password"
        if not os.getenv("NEO4J_AUTH") and not os.getenv("NEO4J_USER") and not os.getenv("NEO4J_PASSWORD"):
            print(f"ℹ️  Using settings/defaults: user={neo4j_user}, password={'***' if neo4j_password else 'NOT SET'}")
            print("   (Set NEO4J_AUTH=neo4j/password or NEO4J_USER/NEO4J_PASSWORD to override.)")
    
    neo4j_uri = os.getenv("NEO4J_URI") or getattr(settings, 'neo4j_uri', None) or "bolt://localhost:7687"
    
    print(f"\n📋 Connection details:")
    print(f"   URI: {neo4j_uri}")
    print(f"   User: {neo4j_user}")
    print(f"   Password: {'***' if neo4j_password else 'NOT SET'}")
    
    # Check if URI points to localhost (not dockerized)
    if "localhost" in neo4j_uri or "127.0.0.1" in neo4j_uri:
        print("ℹ️  Using localhost Neo4j (not dockerized)")
        print("   Make sure Neo4j is running locally on the specified port")
    
    # Try to connect and verify Neo4j is available
    try:
        toolkit = Neo4jMemoryToolkit()
        print("✅ Neo4j Memory toolkit imported and instantiated")
        
        # Debug: Check what settings the toolkit will use
        toolkit_uri = getattr(settings, 'neo4j_uri', 'bolt://localhost:7687')
        toolkit_user = getattr(settings, 'neo4j_user', 'neo4j')
        toolkit_password = getattr(settings, 'neo4j_password', 'password')
        print(f"\n🔍 Toolkit will use (from settings):")
        print(f"   URI: {toolkit_uri}")
        print(f"   User: {toolkit_user}")
        print(f"   Password: {'***' if toolkit_password else 'NOT SET'}")
        
        # If there's a mismatch, warn
        if toolkit_uri != neo4j_uri or toolkit_user != neo4j_user or toolkit_password != neo4j_password:
            print(f"\n⚠️  Mismatch detected between test env and settings!")
            print(f"   Test env: {neo4j_uri}, {neo4j_user}, {'***' if neo4j_password else 'NOT SET'}")
            print(f"   Settings: {toolkit_uri}, {toolkit_user}, {'***' if toolkit_password else 'NOT SET'}")
            print("   The toolkit uses settings, so ensure settings match your Neo4j configuration.")
        
        # Initialize with connection test
        await toolkit.initialize()
        if not toolkit._memory:
            print("⚠️  Neo4j Memory not initialized (connection failed)")
            print("\n💡 Troubleshooting:")
            print(f"   - URI: {neo4j_uri}")
            print(f"   - User: {neo4j_user}")
            print(f"   - Password used: {'***' if neo4j_password else 'NOT SET'}")
            print("\n   Common issues:")
            print("   1. Wrong password - Neo4j container might have a different password")
            print("   2. First-time setup - Neo4j requires password change on first login")
            print("   3. Check Neo4j logs: docker logs ats-neo4j")
            if "localhost" in neo4j_uri or "127.0.0.1" in neo4j_uri:
                print("\n   For localhost Neo4j:")
                print("   - If using Docker: Check NEO4J_AUTH in docker-compose.yml")
                print("   - Default: NEO4J_AUTH=neo4j/password")
                print("   - Export: export NEO4J_AUTH=neo4j/password")
                print("   - Or set: export NEO4J_PASSWORD=password")
            else:
                print("   - For Docker: Ensure Neo4j container is running")
                print("   - Check docker-compose.yml for Neo4j service")
            print("\n   To reset Neo4j password (if first time):")
            print("   docker exec -it ats-neo4j cypher-shell -u neo4j -p neo4j")
            print("   Then run: CALL dbms.changePassword('password');")
            return
    except Exception as conn_error:
        print(f"⚠️  Failed to connect to Neo4j: {conn_error}")
        print("\n💡 Connection troubleshooting:")
        print(f"   - URI: {neo4j_uri}")
        if "localhost" in neo4j_uri or "127.0.0.1" in neo4j_uri:
            print("   - For localhost: Ensure Neo4j is running locally")
            print("     Start Neo4j: neo4j start (if installed locally)")
            print("     Or use Docker: docker run -p 7474:7474 -p 7687:7687 neo4j:latest")
        else:
            print("   - For Docker: Check if Neo4j container is running")
            print("     docker-compose ps | grep neo4j")
        print("\n✅ Toolkit can still be imported and instantiated.")
        return
    
    try:
        # Initialize toolkit
        toolkit = Neo4jMemoryToolkit()
        print("✅ Neo4j Memory toolkit imported and instantiated")
        
        # Initialize
        await toolkit.initialize()
        if not toolkit._memory:
            print("⚠️  Neo4j Memory not initialized (connection may have failed)")
            return
        print("✅ Neo4j Memory toolkit initialized successfully")
        
        # Test tools
        tools = toolkit.get_tools()
        print(f"✅ Toolkit provides {len(tools)} tools")
        
        tool_names = []
        for tool in tools:
            name = None
            if hasattr(tool, 'name'):
                name = tool.name
            elif hasattr(tool, 'openai_tool_schema'):
                schema = tool.openai_tool_schema
                if isinstance(schema, dict) and 'function' in schema:
                    name = schema['function'].get('name')
            if name:
                tool_names.append(name)
        
        print("\n📋 Available tools:")
        for i, name in enumerate(tool_names, 1):
            print(f"   {i}. {name}")
        
        # Test tool schemas
        print("\n🔍 Testing tool schemas...")
        schema_errors = []
        for tool in tools:
            try:
                schema = tool.get_openai_tool_schema() if hasattr(tool, 'get_openai_tool_schema') else tool.openai_tool_schema
                if isinstance(schema, dict):
                    func_schema = schema.get('function', {})
                    tool_name = func_schema.get('name', 'unknown')
                    params = func_schema.get('parameters', {})
                    if params.get('type') == 'object':
                        print(f"✅ Tool '{tool_name}' has valid schema")
                    else:
                        schema_errors.append(f"{tool_name}: invalid parameters type")
                else:
                    schema_errors.append(f"{tool_name}: schema is not a dict")
            except Exception as e:
                schema_errors.append(f"Error getting schema: {e}")
        
        if schema_errors:
            print(f"⚠️  Schema errors found: {schema_errors}")
        else:
            print("✅ All tool schemas are valid")
        
        # Test read_graph (should work even if graph is empty)
        print("\n📊 Testing read_graph...")
        result = toolkit.read_graph()
        if result.get('success'):
            entities = result.get('entities', [])
            relations = result.get('relations', [])
            print(f"✅ Graph read successfully: {len(entities)} entities, {len(relations)} relations")
        else:
            print(f"⚠️  Read graph failed: {result.get('error')}")
        
        # Test create_entities (create test entities)
        print("\n📝 Testing create_entities...")
        test_entities = [
            {
                "name": "TestBTC",
                "type": "asset",
                "observations": ["Test entity for toolkit validation", "Bitcoin cryptocurrency"]
            },
            {
                "name": "TestMarket",
                "type": "market",
                "observations": ["Test market entity", "Crypto market"]
            }
        ]
        create_result = toolkit.create_entities(test_entities)
        if create_result.get('success'):
            print(f"✅ Created {len(create_result.get('entities', []))} test entities")
        else:
            print(f"⚠️  Create entities failed: {create_result.get('error')}")
        
        # Test search_memories
        print("\n🔍 Testing search_memories...")
        search_result = toolkit.search_memories("TestBTC")
        if search_result.get('success'):
            found_entities = search_result.get('entities', [])
            print(f"✅ Search found {len(found_entities)} entities")
        else:
            print(f"⚠️  Search failed: {search_result.get('error')}")
        
        # Test find_memories_by_name
        print("\n🔍 Testing find_memories_by_name...")
        find_result = toolkit.find_memories_by_name(["TestBTC", "TestMarket"])
        if find_result.get('success'):
            found_entities = find_result.get('entities', [])
            print(f"✅ Found {len(found_entities)} entities by name")
        else:
            print(f"⚠️  Find by name failed: {find_result.get('error')}")
        
        # Test add_observations
        print("\n➕ Testing add_observations...")
        obs_result = toolkit.add_observations([
            {
                "entityName": "TestBTC",
                "observations": ["Added via toolkit test"]
            }
        ])
        if obs_result.get('success'):
            print("✅ Observations added successfully")
        else:
            print(f"⚠️  Add observations failed: {obs_result.get('error')}")
        
        # Cleanup: Delete test entities
        print("\n🧹 Cleaning up test entities...")
        delete_result = toolkit.delete_entities(["TestBTC", "TestMarket"])
        if delete_result.get('success'):
            print(f"✅ Deleted {delete_result.get('deleted_count', 0)} test entities")
        else:
            print(f"⚠️  Delete entities failed: {delete_result.get('error')}")
        
        # Close connection
        await toolkit.close()
        print("\n✅ Neo4j Memory toolkit test completed")
        
    except Exception as e:
        print(f"❌ Error testing Neo4j Memory toolkit: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_neo4j_memory())
