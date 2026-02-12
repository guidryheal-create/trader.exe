"""Test script for Polymarket Toolkit."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.camel_tools.polymarket_toolkit import PolymarketToolkit

async def test_polymarket_toolkit():
    """Test Polymarket Toolkit initialization and tools."""
    print("=" * 60)
    print("Testing Polymarket Toolkit")
    print("=" * 60)
    
    try:
        # Initialize toolkit
        toolkit = PolymarketToolkit()
        print("✅ Polymarket toolkit imported and instantiated")
        
        # Test initialization
        await toolkit.initialize()
        print("✅ Toolkit initialized")
        
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
        
        # Verify expected tools
        expected_tools = [
            'get_market_details',
            'get_event_markets',
            'list_active_markets',
            'search_markets',
            'get_markets_by_tag',
            'get_all_tags',
            'get_order_book'
        ]
        for expected in expected_tools:
            if expected in tool_names:
                print(f"✅ Tool '{expected}' found")
            else:
                print(f"⚠️  Tool '{expected}' not found")
        
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
                        props = params.get('properties', {})
                        required = params.get('required', [])
                        strict = params.get('additionalProperties') == False
                        print(f"✅ Tool '{tool_name}' has valid schema ({len(props)} properties, {len(required)} required, strict={strict})")
                    else:
                        schema_errors.append(f"{tool_name}: invalid parameters type")
                else:
                    schema_errors.append(f"schema is not a dict")
            except Exception as e:
                schema_errors.append(f"Error getting schema: {e}")
        
        if schema_errors:
            print(f"⚠️  Schema errors found: {schema_errors}")
        else:
            print("✅ All tool schemas are valid")
        
        # Test client methods (with mocked HTTP responses)
        print("\n🌐 Testing Polymarket client methods...")
        
        # Mock HTTP client
        with patch('core.clients.polymarket_client.httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "id": "test_market_123",
                "question": "Will Bitcoin reach $100k by 2025?",
                "slug": "will-bitcoin-reach-100k-by-2025",
                "tags": ["Crypto", "Bitcoin"]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client
            
            # Test get_market_details
            print("\n📊 Testing get_market_details...")
            result = toolkit.get_market_details(slug="test-market")
            if result.get('success'):
                print(f"✅ get_market_details returned success")
                market = result.get('market', {})
                print(f"   Market ID: {market.get('id')}")
            else:
                print(f"⚠️  get_market_details returned error: {result.get('error')}")
            
            # Test search_markets
            print("\n🔍 Testing search_markets...")
            mock_response.json.return_value = [
                {"id": "market1", "question": "Test Market 1"},
                {"id": "market2", "question": "Test Market 2"}
            ]
            result = toolkit.search_markets(query="bitcoin", limit=10)
            if result.get('success'):
                print(f"✅ search_markets returned success")
                print(f"   Markets found: {result.get('count')}")
            else:
                print(f"⚠️  search_markets returned error: {result.get('error')}")
            
            # Test list_active_markets
            print("\n📋 Testing list_active_markets...")
            result = toolkit.list_active_markets(limit=20, query="")
            if result.get('success'):
                print(f"✅ list_active_markets returned success")
                print(f"   Markets found: {result.get('count')}")
            else:
                print(f"⚠️  list_active_markets returned error: {result.get('error')}")
            
            # Test get_markets_by_tag
            print("\n🏷️  Testing get_markets_by_tag...")
            result = toolkit.get_markets_by_tag(tag="Crypto", limit=10)
            if result.get('success'):
                print(f"✅ get_markets_by_tag returned success")
                print(f"   Tag: {result.get('tag')}")
                print(f"   Markets found: {result.get('count')}")
            else:
                print(f"⚠️  get_markets_by_tag returned error: {result.get('error')}")
            
            # Test get_all_tags
            print("\n🏷️  Testing get_all_tags...")
            mock_response.json.return_value = [
                {"tags": ["Crypto", "Bitcoin"]},
                {"tags": ["Politics", "Election"]},
                {"tags": ["Sports", "NFL"]}
            ]
            result = toolkit.get_all_tags(limit=100)
            if result.get('success'):
                print(f"✅ get_all_tags returned success")
                tags = result.get('tags', [])
                print(f"   Tags found: {result.get('count')}")
                if tags:
                    print(f"   Sample tags: {', '.join(tags[:5])}")
            else:
                print(f"⚠️  get_all_tags returned error: {result.get('error')}")
            
            # Test get_order_book
            print("\n📖 Testing get_order_book...")
            mock_response.json.return_value = {
                "bids": [{"price": "0.5", "size": "100"}, {"price": "0.49", "size": "200"}],
                "asks": [{"price": "0.51", "size": "150"}, {"price": "0.52", "size": "250"}]
            }
            result = toolkit.get_order_book(token_id="test_token_123", depth=20)
            if result.get('success'):
                print(f"✅ get_order_book returned success")
                orderbook = result.get('orderbook', {})
                bids = orderbook.get('bids', [])
                asks = orderbook.get('asks', [])
                print(f"   Bids: {len(bids)}, Asks: {len(asks)}")
            else:
                print(f"⚠️  get_order_book returned error: {result.get('error')}")
            
            # Test get_event_markets
            print("\n📅 Testing get_event_markets...")
            mock_response.json.return_value = {
                "id": "event_123",
                "markets": [
                    {"id": "market1", "question": "Event Market 1"},
                    {"id": "market2", "question": "Event Market 2"}
                ]
            }
            result = toolkit.get_event_markets(event_slug="test-event")
            if result.get('success'):
                print(f"✅ get_event_markets returned success")
                markets = result.get('markets', [])
                print(f"   Markets found: {len(markets)}")
            else:
                print(f"⚠️  get_event_markets returned error: {result.get('error')}")
        
        print("\n✅ Polymarket toolkit test completed")
        
    except Exception as e:
        print(f"❌ Error testing Polymarket toolkit: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_polymarket_toolkit())

