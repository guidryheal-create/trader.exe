"""
Tests for Polymarket Workflow Orchestrator.

Validates:
- Market scanning stage
- Position sizing stage
- Order planning stage
- Full workflow execution
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from core.camel_runtime.polymarket_workflow_orchestrator import PolymarketWorkflowOrchestrator
from core.camel_tools.polymarket_data_toolkit import PolymarketDataToolkit


class TestPolymarketDataToolkit:
    """Test PolymarketDataToolkit for market scanning and sizing."""

    def test_toolkit_initialization(self):
        """Test toolkit initializes correctly."""
        toolkit = PolymarketDataToolkit()
        assert toolkit is not None
        assert toolkit.client is not None
        assert toolkit.timeout == 30.0

    def test_scan_markets_by_category(self):
        """Test market category scanning."""
        toolkit = PolymarketDataToolkit()
        # Avoid network calls
        with patch.object(toolkit.client, "filter_markets_by_category", new=AsyncMock(return_value=[])):
        
            result = toolkit.scan_markets_by_category(
                category="crypto",
                limit=5,
                min_liquidity=1000.0
            )
        
        assert result is not None
        assert "status" in result
        assert "markets" in result
        # May be empty in test environment
        assert isinstance(result["markets"], list)

    def test_search_high_conviction_markets(self):
        """Test high-conviction market search."""
        toolkit = PolymarketDataToolkit()
        # Avoid network calls
        with patch.object(toolkit.client, "search_markets", new=AsyncMock(return_value=[])):
            result = toolkit.search_high_conviction_markets(
                query="bitcoin",
                confidence_threshold=0.65,
                limit=5
            )
        
        assert result is not None
        assert "status" in result
        assert "markets" in result
        assert isinstance(result["markets"], list)

    def test_calculate_position_sizes(self):
        """Test position sizing calculation."""
        toolkit = PolymarketDataToolkit()
        
        mock_markets = [
            {
                "id": "market_1",
                "title": "Bitcoin Price",
                "liquidity": 50000,
                "volume_24h": 30000,
                "mid_price": 0.65,
                "spread": 0.02
            },
            {
                "id": "market_2",
                "title": "ETH Price",
                "liquidity": 30000,
                "volume_24h": 15000,
                "mid_price": 0.50,
                "spread": 0.03
            }
        ]
        
        wallet_dist = {"USDC": 1.0}
        
        result = toolkit.calculate_position_sizes(
            markets=mock_markets,
            wallet_distribution=wallet_dist,
            max_position_size_usd=2000.0,
            max_total_exposure_usd=5000.0
        )
        
        assert result is not None
        assert result["status"] == "success"
        assert "positions" in result
        assert result["total_exposure_usd"] >= 0
        assert result["total_exposure_usd"] <= 5000.0

    def test_position_sizing_respects_limits(self):
        """Test that position sizing respects max exposure limits."""
        toolkit = PolymarketDataToolkit()
        
        mock_markets = [
            {
                "id": f"market_{i}",
                "title": f"Test Market {i}",
                "liquidity": 100000,
                "volume_24h": 50000,
                "mid_price": 0.5,
                "spread": 0.01
            }
            for i in range(10)
        ]
        
        result = toolkit.calculate_position_sizes(
            markets=mock_markets,
            wallet_distribution={"USDC": 1.0},
            max_position_size_usd=1000.0,
            max_total_exposure_usd=3000.0
        )
        
        assert result["total_exposure_usd"] <= 3000.0
        assert all(p["position_size_usd"] <= 1000.0 for p in result["positions"])

    def test_plan_order_batch(self):
        """Test order batch planning."""
        toolkit = PolymarketDataToolkit()
        
        positions = [
            {
                "market_id": "market_1",
                "market_title": "Bitcoin Price",
                "position_size_usd": 1000.0,
                "liquidity": 50000,
                "volume_24h": 30000,
                "max_quantity": 1500,
                "mid_price": 0.67,
                "risk_level": "LOW"
            }
        ]
        
        result = toolkit.plan_order_batch(
            positions=positions,
            order_type="limit",
            price_offset=0.02
        )
        
        assert result is not None
        assert result["status"] == "ready_for_execution"
        assert "orders" in result
        assert len(result["orders"]) > 0
        
        # Verify order structure
        order = result["orders"][0]
        assert order["market_id"] == "market_1"
        assert order["side"] == "BUY"
        assert order["quantity"] > 0
        assert order["price"] > 0


class TestPolymarketWorkflowOrchestrator:
    """Test PolymarketWorkflowOrchestrator."""

    def test_orchestrator_initialization(self):
        """Test orchestrator initializes correctly."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        assert orchestrator is not None
        assert orchestrator.data_toolkit is not None
        assert orchestrator.polymarket_client is not None
        assert orchestrator.forecasting_client is not None
        assert orchestrator.workflow_history == []

    def test_start_trading_workflow(self):
        """Test full trading workflow execution."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        # Mock the toolkit's search to return test data
        with patch.object(orchestrator.data_toolkit, 'search_high_conviction_markets') as mock_search:
            mock_search.return_value = {
                "status": "success",
                "markets": [
                    {
                        "id": "market_1",
                        "title": "Bitcoin Price Test",
                        "liquidity": 50000,
                        "volume_24h": 30000,
                        "mid_price": 0.65,
                        "spread": 0.02,
                        "confidence_score": 0.8
                    }
                ]
            }
            
            result = orchestrator.start_trading_workflow(
                search_query="bitcoin",
                category=None,
                max_total_exposure=5000.0
            )
            
            assert result is not None
            assert result["status"] == "completed"
            assert "workflow_id" in result
            assert "stages" in result
            assert "scanning" in result["stages"]

    def test_workflow_history(self):
        """Test workflow history tracking."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        with patch.object(orchestrator.data_toolkit, 'search_high_conviction_markets') as mock_search:
            mock_search.return_value = {
                "status": "success",
                "markets": []
            }
            
            # Run multiple workflows
            result1 = orchestrator.start_trading_workflow()
            result2 = orchestrator.start_trading_workflow()
            
            history = orchestrator.get_workflow_history()
            
            assert len(history) >= 2
            assert history[0]["workflow_id"] != history[1]["workflow_id"]

    def test_get_workflow_status(self):
        """Test retrieving workflow status."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        with patch.object(orchestrator.data_toolkit, 'search_high_conviction_markets') as mock_search:
            mock_search.return_value = {
                "status": "success",
                "markets": []
            }
            
            result = orchestrator.start_trading_workflow()
            workflow_id = result["workflow_id"]
            
            status = orchestrator.get_workflow_status(workflow_id)
            
            assert status["workflow_id"] == workflow_id
            assert status["status"] in ["completed", "failed", "in_progress"]

    def test_workflow_summary(self):
        """Test workflow summary generation."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        summary = orchestrator.get_summary()
        
        assert "total_workflows" in summary
        assert "completed" in summary
        assert "failed" in summary
        assert "mode" in summary
        assert summary["total_workflows"] == 0

    def test_market_scanning_stage(self):
        """Test market scanning stage."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        result = orchestrator._stage_market_scanning(
            search_query="crypto",
            category="crypto"
        )
        
        assert result["stage"] == "scanning"
        assert "status" in result
        assert "markets" in result
        assert isinstance(result["markets"], list)

    def test_position_sizing_stage(self):
        """Test position sizing stage."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        markets = [
            {
                "id": "market_1",
                "title": "Test Market",
                "liquidity": 50000,
                "volume_24h": 30000,
                "mid_price": 0.65,
                "spread": 0.02
            }
        ]
        
        result = orchestrator._stage_position_sizing(markets, 5000.0)
        
        assert result["stage"] == "sizing"
        assert result["status"] == "completed"
        assert "positions" in result
        assert "total_exposure" in result

    def test_order_planning_stage(self):
        """Test order planning stage."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        positions = [
            {
                "market_id": "market_1",
                "market_title": "Test Market",
                "position_size_usd": 1000.0,
                "liquidity": 50000,
                "volume_24h": 30000,
                "max_quantity": 1500,
                "mid_price": 0.67,
                "risk_level": "LOW"
            }
        ]
        
        result = orchestrator._stage_order_planning(positions)
        
        assert result["stage"] == "planning"
        assert result["status"] == "completed"
        assert "orders" in result

    def test_execution_planning_stage(self):
        """Test execution planning stage."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        orders = [
            {
                "market_id": "market_1",
                "side": "BUY",
                "quantity": 1500,
                "price": 0.65,
                "order_type": "limit"
            }
        ]
        
        result = orchestrator._stage_execution_planning(orders)
        
        assert result["stage"] == "execution_plan"
        assert result["status"] == "completed"
        assert "orders" in result
        assert result["execution_ready"] is True


class TestWorkflowIntegration:
    """Integration tests for full workflow."""

    def test_full_workflow_with_mock_data(self):
        """Test complete workflow with mocked data."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        # Mock market search
        mock_markets = [
            {
                "id": f"market_{i}",
                "title": f"Market {i}",
                "liquidity": 50000 - i * 5000,
                "volume_24h": 30000 - i * 3000,
                "mid_price": 0.65 - i * 0.05,
                "spread": 0.02 + i * 0.01,
                "confidence_score": 0.8 - i * 0.1
            }
            for i in range(3)
        ]
        
        with patch.object(orchestrator.data_toolkit, 'search_high_conviction_markets') as mock_search:
            mock_search.return_value = {
                "status": "success",
                "markets": mock_markets
            }
            
            result = orchestrator.start_trading_workflow(
                search_query="test market",
                max_total_exposure=5000.0
            )
            
            assert result["status"] == "completed"
            assert "scanning" in result["stages"]
            assert "sizing" in result["stages"]
            assert "planning" in result["stages"]
            assert "execution_plan" in result["stages"]
            
            # Verify all stages completed
            for stage_name in ["scanning", "sizing", "planning", "execution_plan"]:
                stage = result["stages"][stage_name]
                assert stage["status"] == "completed"

    def test_workflow_error_handling(self):
        """Test workflow error handling."""
        orchestrator = PolymarketWorkflowOrchestrator()
        
        # Mock search to fail
        with patch.object(orchestrator.data_toolkit, 'search_high_conviction_markets') as mock_search:
            mock_search.return_value = {
                "status": "error",
                "message": "API Error"
            }
            
            result = orchestrator.start_trading_workflow()
            
            assert result["status"] == "failed"
            assert "error" in result
