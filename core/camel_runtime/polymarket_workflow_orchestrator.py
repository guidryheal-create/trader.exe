"""
Polymarket Trading Workflow Orchestrator for CAMEL Workforce.

Coordinates multi-agent tasks:
1. Market Scanning Agent - Finds high-conviction markets
2. Position Sizing Agent - Calculates risk-adjusted positions
3. Execution Agent - Places mock orders (DEMO_MODE) or real orders
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import asyncio
import os
from datetime import datetime
import logging
import uuid

from core.logging import log
from core.clients.polymarket_client import PolymarketClient
from core.clients.forecasting_client import ForecastingClient
from core.camel_tools.polymarket_data_toolkit import PolymarketDataToolkit

logger = logging.getLogger(__name__)


class PolymarketWorkflowOrchestrator:
    """Orchestrates Polymarket trading workflow across CAMEL agents."""

    def __init__(
        self,
        data_toolkit: Optional[PolymarketDataToolkit] = None,
        polymarket_client: Optional[PolymarketClient] = None,
        forecasting_client: Optional[ForecastingClient] = None,
    ):
        """Initialize workflow orchestrator.
        
        Args:
            data_toolkit: PolymarketDataToolkit instance (created if None)
            polymarket_client: PolymarketClient instance (created if None)
            forecasting_client: ForecastingClient instance (created if None)
        """
        self.data_toolkit = data_toolkit or PolymarketDataToolkit()
        self.polymarket_client = polymarket_client or PolymarketClient()
        self.forecasting_client = forecasting_client or ForecastingClient({})
        
        self.workflow_history: List[Dict[str, Any]] = []
        self.current_workflow_id: Optional[str] = None
        
        log.info("PolymarketWorkflowOrchestrator initialized")

    # ========================================================================
    # WORKFLOW ORCHESTRATION
    # ========================================================================

    def start_trading_workflow(
        self,
        search_query: str = "prediction markets",
        category: Optional[str] = None,
        max_total_exposure: float = 5000.0,
    ) -> Dict[str, Any]:
        """Start full trading workflow: scan → size → plan → execute.
        
        Args:
            search_query: Market search query
            category: Market category filter (optional)
            max_total_exposure: Max total portfolio exposure
            
        Returns:
            Workflow execution result
        """
        self.current_workflow_id = self._generate_workflow_id()
        
        log.info(f"Starting trading workflow: {self.current_workflow_id}")
        
        workflow_result = {
            "workflow_id": self.current_workflow_id,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "in_progress",
            "stages": {}
        }
        
        try:
            # Stage 1: Market Scanning
            log.info("Stage 1: Market Scanning")
            scan_result = self._stage_market_scanning(search_query, category)
            workflow_result["stages"]["scanning"] = scan_result
            
            if not scan_result.get("markets"):
                workflow_result["status"] = "failed"
                workflow_result["error"] = "No markets found"
                self.workflow_history.append(workflow_result)
                return workflow_result
            
            # Stage 2: Position Sizing
            log.info("Stage 2: Position Sizing")
            sizing_result = self._stage_position_sizing(
                scan_result["markets"],
                max_total_exposure
            )
            workflow_result["stages"]["sizing"] = sizing_result
            
            # Stage 3: Order Planning
            log.info("Stage 3: Order Planning")
            planning_result = self._stage_order_planning(
                sizing_result["positions"]
            )
            workflow_result["stages"]["planning"] = planning_result
            
            # Stage 4: Mock Execution (or real execution if not DEMO_MODE)
            log.info("Stage 4: Execution Planning")
            execution_result = self._stage_execution_planning(
                planning_result["orders"]
            )
            workflow_result["stages"]["execution_plan"] = execution_result
            
            workflow_result["status"] = "completed"
            
        except Exception as e:
            log.error(f"Workflow error: {e}")
            workflow_result["status"] = "failed"
            workflow_result["error"] = str(e)
        
        self.workflow_history.append(workflow_result)
        return workflow_result

    # ========================================================================
    # WORKFLOW STAGES
    # ========================================================================

    def _stage_market_scanning(
        self,
        search_query: str,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stage 1: Market Scanning Agent.
        
        Responsibilities:
        - Search for high-conviction markets
        - Filter by confidence threshold
        - Return top candidates
        """
        log.info(f"Scanning markets: query='{search_query}', category={category}")
        
        result = {
            "stage": "scanning",
            "status": "completed",
            "markets": []
        }
        
        try:
            # Search high-conviction markets
            search_result = self.data_toolkit.search_high_conviction_markets(
                query=search_query,
                confidence_threshold=0.65,
                limit=10
            )
            
            if search_result.get("status") == "success":
                result["markets"] = search_result.get("markets", [])
                result["query"] = search_query
                result["markets_found"] = len(result["markets"])
            else:
                result["status"] = "failed"
                result["error"] = search_result.get("message", "Search failed")
            
            # Optional: Filter by category
            if category:
                category_result = self.data_toolkit.scan_markets_by_category(
                    category=category,
                    limit=20,
                    min_liquidity=1000.0
                )
                
                if category_result.get("status") == "success":
                    result["category_markets"] = category_result.get("markets", [])
                    result["category"] = category
        
        except Exception as e:
            log.error(f"Scanning stage error: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
        
        return result

    def _stage_position_sizing(
        self,
        markets: List[Dict[str, Any]],
        max_total_exposure: float
    ) -> Dict[str, Any]:
        """Stage 2: Position Sizing Agent.
        
        Responsibilities:
        - Calculate position sizes based on risk limits
        - Apply Kelly criterion / portfolio optimization
        - Return position plan
        """
        log.info(f"Sizing positions: {len(markets)} markets, max exposure ${max_total_exposure}")
        
        result = {
            "stage": "sizing",
            "status": "completed",
            "positions": []
        }
        
        try:
            # Mock wallet distribution
            wallet_dist = {
                "USDC": 1.0  # All USDC for prediction markets
            }
            
            sizing_result = self.data_toolkit.calculate_position_sizes(
                markets=markets,
                wallet_distribution=wallet_dist,
                max_position_size_usd=2000.0,
                max_total_exposure_usd=max_total_exposure
            )
            
            if sizing_result.get("status") == "success":
                result["positions"] = sizing_result.get("positions", [])
                result["total_exposure"] = sizing_result.get("total_exposure_usd", 0)
                result["utilization_percent"] = sizing_result.get("utilization_percent", 0)
            else:
                result["status"] = "failed"
                result["error"] = sizing_result.get("message", "Sizing failed")
        
        except Exception as e:
            log.error(f"Sizing stage error: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
        
        return result

    def _stage_order_planning(
        self,
        positions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Stage 3: Order Planning Agent.
        
        Responsibilities:
        - Convert positions to orders
        - Set order parameters (price, quantity, type)
        - Validate order compliance
        """
        log.info(f"Planning orders: {len(positions)} positions")
        
        result = {
            "stage": "planning",
            "status": "completed",
            "orders": []
        }
        
        try:
            planning_result = self.data_toolkit.plan_order_batch(
                positions=positions,
                order_type="limit",
                price_offset=0.02
            )
            
            if planning_result.get("status") == "ready_for_execution":
                result["orders"] = planning_result.get("orders", [])
                result["order_count"] = planning_result.get("order_count", 0)
                result["estimated_cost"] = planning_result.get(
                    "estimated_total_cost_usd", 0
                )
            else:
                result["status"] = "failed"
                result["error"] = planning_result.get("message", "Planning failed")
        
        except Exception as e:
            log.error(f"Planning stage error: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
        
        return result

    def _stage_execution_planning(
        self,
        orders: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Stage 4: Execution Planning.
        
        Responsibilities:
        - Validate orders for execution
        - Set execution parameters
        - Return execution plan (mock or real)
        """
        log.info(f"Planning execution: {len(orders)} orders")
        
        result = {
            "stage": "execution_plan",
            "status": "completed",
            "orders": orders,
            "mode": "DEMO" if os.getenv("DEMO_MODE", "").upper() == "TRUE" else "LIVE",
            "execution_ready": True
        }
        
        # Add execution instructions
        if os.getenv("DEMO_MODE", "").upper() == "TRUE":
            result["note"] = "DEMO_MODE enabled - no real orders will be placed"
            result["simulation"] = True
        else:
            result["note"] = "LIVE_MODE - orders will be placed on Polymarket"
            result["simulation"] = False
            result["warning"] = "Use with caution in production"
        
        return result

    # ========================================================================
    # WORKFLOW STATUS & MONITORING
    # ========================================================================

    def get_workflow_status(self, workflow_id: Optional[str] = None) -> Dict[str, Any]:
        """Get status of a workflow.
        
        Args:
            workflow_id: Workflow ID (current if None)
            
        Returns:
            Workflow status details
        """
        wf_id = workflow_id or self.current_workflow_id
        
        if not wf_id:
            return {"error": "No workflow ID specified"}
        
        # Find workflow in history
        for wf in self.workflow_history:
            if wf["workflow_id"] == wf_id:
                return wf
        
        return {"error": f"Workflow {wf_id} not found"}

    def get_workflow_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent workflow history.
        
        Args:
            limit: Maximum workflows to return
            
        Returns:
            List of workflows (most recent first)
        """
        return list(reversed(self.workflow_history[-limit:]))

    # ========================================================================
    # UTILITIES
    # ========================================================================

    def _generate_workflow_id(self) -> str:
        """Generate unique workflow ID."""
        return f"workflow_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    def reset_history(self) -> None:
        """Clear workflow history."""
        self.workflow_history = []
        self.current_workflow_id = None
        log.info("Workflow history cleared")

    def get_summary(self) -> Dict[str, Any]:
        """Get workflow orchestrator summary.
        
        Returns:
            Summary statistics
        """
        completed = sum(
            1 for wf in self.workflow_history 
            if wf.get("status") == "completed"
        )
        failed = sum(
            1 for wf in self.workflow_history 
            if wf.get("status") == "failed"
        )
        
        return {
            "total_workflows": len(self.workflow_history),
            "completed": completed,
            "failed": failed,
            "current_workflow_id": self.current_workflow_id,
            "mode": "DEMO" if os.getenv("DEMO_MODE", "").upper() == "TRUE" else "LIVE",
            "forecasting_api_url": self.forecasting_client.base_url,
        }
