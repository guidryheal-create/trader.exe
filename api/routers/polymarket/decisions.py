"""Polymarket router package - Agentic decision tracking"""
from fastapi import APIRouter, Query, HTTPException

from api.services.polymarket.decision_service import decision_service

router = APIRouter()


@router.get("/decisions")
async def list_decisions(limit: int = Query(50, ge=1, le=500)):
    """
    Get decision history
    
    Args:
        limit: Number of recent decisions to return
    
    Returns:
        List of agentic decisions with reasoning and outcomes
    """
    return {"decisions": decision_service.list_decisions(limit=limit), "limit": limit}


@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: str):
    """
    Get details of a specific decision
    
    Args:
        decision_id: Decision identifier
    
    Returns:
        Decision details including reasoning, confidence, execution result
    """
    decision = decision_service.get_decision(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision


@router.get("/decisions/by-market/{market_id}")
async def get_market_decisions(market_id: str, limit: int = Query(20, ge=1, le=200), bet_id: str | None = None):
    """
    Get decisions for a specific Polymarket market (or bet_id).
    
    Args:
        market_id: Polymarket market ID
        bet_id: Optional LLM-safe bet identifier
        limit: Number of recent decisions
    
    Returns:
        Decisions for this market/bet
    """
    decisions = [
        d for d in decision_service.list_decisions(limit=limit)
        if d.get("market_id") == market_id or (bet_id and d.get("bet_id") == bet_id)
    ]
    return {"market_id": market_id, "bet_id": bet_id, "decisions": decisions}


@router.get("/decisions/performance")
async def get_decision_performance():
    """
    Get performance metrics for agentic decisions
    
    Returns:
        Decision accuracy, win rate, average confidence
    """
    decisions = decision_service.list_decisions(limit=500)
    total = len(decisions)
    avg_conf = sum(d.get("confidence", 0) for d in decisions) / total if total else 0
    return {"total": total, "average_confidence": avg_conf}




@router.post("/decisions/export")
async def export_decisions(format: str = Query("json", pattern="^(json|csv)$")):
    """
    Export decision history
    
    Args:
        format: Export format (json or csv)
    
    Returns:
        Exported decisions
    """
    decisions = decision_service.list_decisions(limit=1000)
    return {"format": format, "decisions": decisions}
