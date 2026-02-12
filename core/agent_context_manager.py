"""
Agent Context Manager

Manages context data flow between agents, ensuring:
1. Each agent has proper context (trend, fact, risk data)
2. Memory is shared appropriately (daily workforce memory)
3. Trend tables are properly formatted
4. No blind HOLD defaults (always compute from distributions)

This is the single source of truth for:
- What context each agent needs
- How to prepare data for agent consumption
- How to extract and transform agent outputs
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import json

from core.logging import log
from core.models import TrendAssessment, FactInsight, RiskMetrics, TradeAction


class AgentContextData:
    """Rich context data passed to agents."""

    def __init__(self, ticker: str, interval: str = "hours", strategy_mode: str = "default"):
        self.ticker = ticker
        self.interval = interval
        self.strategy_mode = strategy_mode
        
        # Trend context
        self.trend_data: Optional[TrendAssessment] = None
        self.trend_history: List[Dict[str, Any]] = []  # [date, real|null, pred]
        
        # Fact context
        self.fact_data: Optional[FactInsight] = None
        self.recent_news: List[Dict[str, Any]] = []
        self.sentiment_score: float = 0.0
        
        # Risk context
        self.risk_data: Optional[RiskMetrics] = None
        self.volatility: float = 0.0
        self.risk_level: str = "UNKNOWN"
        
        # Memory context
        self.memory_records: List[Dict[str, Any]] = []  # Previous decisions, patterns
        self.similar_patterns: List[str] = []  # Pattern lookup results
        
        # Previous decision context
        self.previous_decision: Optional[Dict[str, Any]] = None
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for agent consumption."""
        return {
            "ticker": self.ticker,
            "interval": self.interval,
            "strategy_mode": self.strategy_mode,
            "trend": self.trend_data.model_dump(mode="json") if self.trend_data else None,
            "trend_history": self.trend_history,
            "fact": self.fact_data.model_dump(mode="json") if self.fact_data else None,
            "recent_news": self.recent_news,
            "sentiment_score": self.sentiment_score,
            "risk": self.risk_data.model_dump(mode="json") if self.risk_data else None,
            "volatility": self.volatility,
            "risk_level": self.risk_level,
            "memory_records": self.memory_records,
            "similar_patterns": self.similar_patterns,
            "previous_decision": self.previous_decision,
        }


class ActionDeterminizer:
    """
    Ensures actions are never blind HOLD defaults.
    
    If no explicit action is provided, derives from distribution:
    - Argmax of distribution
    - If distribution missing, uses confidence + score to infer
    - Last resort: raises error (don't default to HOLD)
    """

    @staticmethod
    def determine_action(
        data: Dict[str, Any],
        ticker: str,
    ) -> str:
        """
        Determine trading action, never defaulting to HOLD.
        
        Args:
            data: Response data from agent/endpoint
            ticker: For logging
            
        Returns:
            Action string: "BUY", "SELL", or "HOLD" (only if computed, never default)
            
        Raises:
            ValueError: If no valid action can be determined from data
        """
        
        # 1. Try explicit action field first
        if "action" in data and data["action"]:
            action = data["action"]
            if isinstance(action, int):
                action_names = {0: "SELL", 1: "HOLD", 2: "BUY"}
                return action_names.get(action)
            if isinstance(action, str) and action in ["BUY", "SELL", "HOLD"]:
                return action
        
        # 2. Try action_name field
        if "action_name" in data and data["action_name"] in ["BUY", "SELL", "HOLD"]:
            return data["action_name"]
        
        # 3. Derive from distribution (most reliable)
        if "distribution" in data and isinstance(data["distribution"], dict):
            dist = data["distribution"]
            if all(k in dist for k in ["BUY", "SELL", "HOLD"]):
                # Argmax of distribution
                action = max(dist.items(), key=lambda x: x[1])[0]
                log.info(
                    f"[ACTION DETERMINIZER] {ticker}: Derived action from distribution. "
                    f"Distribution: BUY={dist.get('BUY', 0):.3f}, "
                    f"HOLD={dist.get('HOLD', 0):.3f}, "
                    f"SELL={dist.get('SELL', 0):.3f} → {action}"
                )
                return action
        
        # 4. Try decision_distribution field
        if "decision_distribution" in data and isinstance(data["decision_distribution"], dict):
            dist = data["decision_distribution"]
            if any(k in dist for k in ["BUY", "SELL", "HOLD"]):
                action = max(dist.items(), key=lambda x: x[1])[0]
                log.info(
                    f"[ACTION DETERMINIZER] {ticker}: Derived action from decision_distribution → {action}"
                )
                return action
        
        # 5. Try q_values (DQN-style)
        if "q_values" in data and isinstance(data["q_values"], (list, tuple)):
            q_vals = data["q_values"]
            if len(q_vals) >= 3:
                # Assuming [SELL, HOLD, BUY]
                q_index = max(range(len(q_vals)), key=lambda i: q_vals[i])
                actions = ["SELL", "HOLD", "BUY"]
                action = actions[q_index] if q_index < len(actions) else None
                if action:
                    log.info(
                        f"[ACTION DETERMINIZER] {ticker}: Derived action from Q-values. "
                        f"Q-values: SELL={q_vals[0]:.3f}, HOLD={q_vals[1]:.3f}, BUY={q_vals[2] if len(q_vals) > 2 else 0:.3f} → {action}"
                    )
                    return action
        
        # 6. Derive from confidence + score
        confidence = data.get("confidence", 0.0)
        score = data.get("blended_score") or data.get("score", 0.0)
        
        if confidence > 0.3 and score is not None:
            if score > 0.2:
                action = "BUY"
            elif score < -0.2:
                action = "SELL"
            else:
                action = "HOLD"
            log.info(
                f"[ACTION DETERMINIZER] {ticker}: Derived action from confidence + score. "
                f"confidence={confidence:.2f}, score={score:.3f} → {action}"
            )
            return action
        
        # 7. Cannot determine - raise error instead of blind HOLD
        log.error(
            f"[ACTION DETERMINIZER] {ticker}: Cannot determine action from data. "
            f"Keys available: {list(data.keys())}. "
            f"Data: {json.dumps({k: v for k, v in data.items() if k not in ['components', 'details']}, default=str, indent=2)}"
        )
        
        raise ValueError(
            f"Cannot determine trading action for {ticker}. "
            f"Expected one of: action, action_name, distribution, decision_distribution, or q_values. "
            f"Got: {list(data.keys())}"
        )

    @staticmethod
    def get_distribution(
        data: Dict[str, Any],
        ticker: str,
    ) -> Dict[str, float]:
        """
        Get decision distribution, creating one if needed.
        
        Args:
            data: Response data
            ticker: For logging
            
        Returns:
            Distribution dict with BUY, HOLD, SELL keys
        """
        
        # 1. Try explicit distribution field
        if "distribution" in data and isinstance(data["distribution"], dict):
            dist = data["distribution"]
            if all(k in dist for k in ["BUY", "SELL", "HOLD"]):
                return dist
        
        # 2. Try decision_distribution
        if "decision_distribution" in data and isinstance(data["decision_distribution"], dict):
            return data["decision_distribution"]
        
        # 3. Derive from Q-values
        if "q_values" in data and isinstance(data["q_values"], (list, tuple)):
            q_vals = data["q_values"]
            if len(q_vals) >= 3:
                # Softmax Q-values to get probabilities
                import numpy as np
                try:
                    q_array = np.array(q_vals[:3], dtype=float)
                    q_array = q_array - np.max(q_array)  # Numerical stability
                    exp_q = np.exp(q_array)
                    dist_vals = exp_q / np.sum(exp_q)
                    return {
                        "SELL": float(dist_vals[0]),
                        "HOLD": float(dist_vals[1]),
                        "BUY": float(dist_vals[2]),
                    }
                except Exception as e:
                    log.warning(f"[ACTION DETERMINIZER] Failed to compute softmax for {ticker}: {e}")
        
        # 4. Create uniform distribution as last resort
        log.warning(
            f"[ACTION DETERMINIZER] {ticker}: No distribution found, using uniform. "
            f"Available keys: {list(data.keys())}"
        )
        return {
            "BUY": 0.333,
            "HOLD": 0.334,
            "SELL": 0.333,
        }


class AgentMemoryCoordinator:
    """Coordinates memory sharing between agents in workforce."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def get_workspace_memory(
        self,
        ticker: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get shared workspace memory for all agents on this ticker.
        
        Used by all agents (Trend, Fact, Memory, Fusion) for daily decisions.
        """
        try:
            memory_key = f"workspace:memory:{ticker}"
            records = await self.redis.lrange(memory_key, -limit, -1)
            return [json.loads(r) for r in records if r]
        except Exception as e:
            log.warning(f"[MEMORY COORDINATOR] Failed to get workspace memory for {ticker}: {e}")
            return []

    async def write_workspace_memory(
        self,
        ticker: str,
        record: Dict[str, Any],
        max_len: int = 100,
    ) -> None:
        """
        Write to shared workspace memory (used by Memory/Fusion agents).
        """
        try:
            memory_key = f"workspace:memory:{ticker}"
            record["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            # Push to list
            await self.redis.rpush(memory_key, json.dumps(record))
            
            # Trim to max length
            await self.redis.ltrim(memory_key, -max_len, -1)
            
            # Set expiry (24 hours)
            await self.redis.expire(memory_key, 86400)
            
        except Exception as e:
            log.warning(f"[MEMORY COORDINATOR] Failed to write workspace memory for {ticker}: {e}")

    async def get_agent_context(
        self,
        ticker: str,
        redis_client,
    ) -> AgentContextData:
        """
        Assemble complete context data for all agents.
        
        Fetches trend, fact, risk, memory all in one call.
        """
        context = AgentContextData(ticker)
        
        try:
            from core.pipelines import (
                get_trend_assessment,
                get_fact_insight,
            )
            
            # Get all agent data in parallel
            trend = await get_trend_assessment(redis_client, ticker)
            fact = await get_fact_insight(redis_client, ticker)
            risk_payload = await redis_client.get_json(f"risk:asset:{ticker}")
            
            if trend:
                context.trend_data = trend
                context.trend_history = trend.supporting_signals.get("trend_history", [])
            
            if fact:
                context.fact_data = fact
                context.sentiment_score = fact.sentiment_score
            
            if risk_payload:
                try:
                    context.risk_data = RiskMetrics(**risk_payload)
                    context.volatility = risk_payload.get("volatility", 0.0)
                    context.risk_level = risk_payload.get("risk_level", "UNKNOWN")
                except Exception as e:
                    log.warning(f"[MEMORY COORDINATOR] Failed to parse risk data for {ticker}: {e}")
            
            # Get previous decision for context
            from core.pipelines import get_fusion_recommendation
            prev_rec = await get_fusion_recommendation(redis_client, ticker)
            if prev_rec:
                context.previous_decision = prev_rec.model_dump(mode="json")
            
            # Get workspace memory
            context.memory_records = await self.get_workspace_memory(ticker, limit=5)
            
        except Exception as e:
            log.warning(f"[MEMORY COORDINATOR] Failed to assemble context for {ticker}: {e}")
        
        return context

