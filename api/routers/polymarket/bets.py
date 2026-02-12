"""Bets router - List, track, and analyze all placed bets on Polymarket"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException, Depends, Request

from api.middleware.auth import verify_auth_header, check_client_rate_limit
from api.services.polymarket.logging_service import logging_service
from api.services.polymarket.decision_service import decision_service
from core.logging import log

router = APIRouter()


@router.get("/bets", dependencies=[Depends(check_client_rate_limit)])
async def list_bets(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None, regex="^(active|closed|pending)$"),
    sort: str = Query("recent", regex="^(recent|confidence|roi|size)$"),
) -> Dict[str, Any]:
    """
    List all placed bets on Polymarket.
    
    ✅ Requires authentication: Authorization: Bearer <api_key>
    
    Args:
        limit: Number of bets to return (default 50, max 500)
        status: Filter by bet status (active, closed, pending)
        sort: Sort order (recent, confidence, roi, size)
    
    Returns:
        List of bets with metadata, ROI, confidence scores
    """
    try:
        await verify_auth_header(request)
    except HTTPException:
        raise
    
    log.info(f"[BETS API] Listing bets (limit={limit}, status={status}, sort={sort})")
    
    # Get decisions which track bets
    all_decisions = decision_service.list_decisions(limit=min(limit * 2, 500))
    
    # Filter to only bet decisions
    bets = []
    for decision in all_decisions:
        if decision.get("decision_type") == "BET" or decision.get("bet_id"):
            bet = {
                "bet_id": decision.get("bet_id", decision.get("decision_id")),
                "market_id": decision.get("market_id"),
                "market_name": decision.get("market_name"),
                "side": decision.get("side", decision.get("position")),  # YES or NO
                "confidence": decision.get("confidence", 0),
                "size": decision.get("size", decision.get("shares", 0)),
                "price": decision.get("price", 0.5),
                "status": decision.get("status", "active"),
                "roi": decision.get("roi"),
                "reasoning": decision.get("reasoning", ""),
                "executed_at": decision.get("executed_at", decision.get("timestamp")),
                "decision_id": decision.get("decision_id"),
            }
            
            # Filter by status if requested
            if status and bet["status"] != status:
                continue
            
            bets.append(bet)
    
    # Sort results
    if sort == "confidence":
        bets.sort(key=lambda b: b["confidence"], reverse=True)
    elif sort == "roi":
        bets.sort(key=lambda b: b["roi"] or 0, reverse=True)
    elif sort == "size":
        bets.sort(key=lambda b: b["size"], reverse=True)
    else:  # recent
        bets.sort(key=lambda b: b["executed_at"], reverse=True)
    
    # Apply limit
    bets = bets[:limit]
    
    log.info(f"[BETS API] Returning {len(bets)} bets")
    
    return {
        "bets": bets,
        "count": len(bets),
        "limit": limit,
        "status_filter": status,
        "sort": sort,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/bets/{bet_id}", dependencies=[Depends(check_client_rate_limit)])
async def get_bet_details(
    request: Request,
    bet_id: str,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific bet.
    
    ✅ Requires authentication: Authorization: Bearer <api_key>
    
    Args:
        bet_id: Bet identifier (usually market_id or decision_id)
    
    Returns:
        Detailed bet information including order book, market data, execution details
    """
    try:
        await verify_auth_header(request)
    except HTTPException:
        raise
    
    log.info(f"[BETS API] Getting details for bet {bet_id}")
    
    # Search for bet in decisions
    all_decisions = decision_service.list_decisions(limit=500)
    
    bet_decision = None
    for decision in all_decisions:
        if decision.get("bet_id") == bet_id or decision.get("decision_id") == bet_id:
            bet_decision = decision
            break
    
    if not bet_decision:
        raise HTTPException(status_code=404, detail=f"Bet {bet_id} not found")
    
    return {
        "bet_id": bet_id,
        "market_id": bet_decision.get("market_id"),
        "market_name": bet_decision.get("market_name"),
        "side": bet_decision.get("side", "UNKNOWN"),
        "confidence": bet_decision.get("confidence", 0),
        "size": bet_decision.get("size", 0),
        "price": bet_decision.get("price", 0.5),
        "status": bet_decision.get("status", "UNKNOWN"),
        "roi": bet_decision.get("roi"),
        "roi_percent": bet_decision.get("roi_percent"),
        "reasoning": bet_decision.get("reasoning", ""),
        "agent_input": bet_decision.get("agent_input", {}),
        "agent_output": bet_decision.get("agent_output", {}),
        "executed_at": bet_decision.get("executed_at", bet_decision.get("timestamp")),
        "completed_at": bet_decision.get("completed_at"),
        "order_details": bet_decision.get("order_details", {}),
        "error": bet_decision.get("error"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/bets/stats/summary", dependencies=[Depends(check_client_rate_limit)])
async def get_bet_summary_stats(
    request: Request,
) -> Dict[str, Any]:
    """
    Get summary statistics for all bets.
    
    ✅ Requires authentication: Authorization: Bearer <api_key>
    
    Returns:
        Summary stats: total bets, win rate, average confidence, total ROI
    """
    try:
        await verify_auth_header(request)
    except HTTPException:
        raise
    
    log.info("[BETS API] Getting bet summary statistics")
    
    all_decisions = decision_service.list_decisions(limit=500)
    bets = [d for d in all_decisions if d.get("decision_type") == "BET" or d.get("bet_id")]
    
    if not bets:
        return {
            "total_bets": 0,
            "active_bets": 0,
            "closed_bets": 0,
            "win_rate": 0,
            "avg_confidence": 0,
            "avg_roi": 0,
            "total_roi": 0,
            "largest_win": 0,
            "largest_loss": 0,
        }
    
    closed_bets = [b for b in bets if b.get("status") == "closed"]
    won_bets = [b for b in closed_bets if b.get("roi", 0) > 0]
    
    total_roi = sum(b.get("roi", 0) for b in closed_bets)
    avg_confidence = sum(b.get("confidence", 0) for b in bets) / len(bets) if bets else 0
    avg_roi = total_roi / len(closed_bets) if closed_bets else 0
    
    win_rate = len(won_bets) / len(closed_bets) if closed_bets else 0
    
    largest_win = max((b.get("roi", 0) for b in closed_bets), default=0)
    largest_loss = min((b.get("roi", 0) for b in closed_bets), default=0)
    
    return {
        "total_bets": len(bets),
        "active_bets": len([b for b in bets if b.get("status") == "active"]),
        "closed_bets": len(closed_bets),
        "pending_bets": len([b for b in bets if b.get("status") == "pending"]),
        "win_rate": round(win_rate, 2),
        "avg_confidence": round(avg_confidence, 2),
        "avg_roi": round(avg_roi, 2),
        "total_roi": round(total_roi, 2),
        "largest_win": round(largest_win, 2),
        "largest_loss": round(largest_loss, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/bets/recent/active", dependencies=[Depends(check_client_rate_limit)])
async def get_active_bets(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    """
    Get currently active (non-closed) bets.
    
    ✅ Requires authentication: Authorization: Bearer <api_key>
    
    Args:
        limit: Maximum number of active bets to return
    
    Returns:
        List of active bets with real-time status
    """
    try:
        await verify_auth_header(request)
    except HTTPException:
        raise
    
    log.info(f"[BETS API] Getting active bets (limit={limit})")
    
    all_decisions = decision_service.list_decisions(limit=500)
    bets = [d for d in all_decisions if d.get("decision_type") == "BET" or d.get("bet_id")]
    
    active_bets = [
        {
            "bet_id": b.get("bet_id", b.get("decision_id")),
            "market_id": b.get("market_id"),
            "market_name": b.get("market_name"),
            "side": b.get("side", "UNKNOWN"),
            "confidence": b.get("confidence", 0),
            "size": b.get("size", 0),
            "price": b.get("price", 0.5),
            "current_price": b.get("current_price", b.get("price", 0.5)),
            "unrealized_roi": b.get("unrealized_roi"),
            "executed_at": b.get("executed_at", b.get("timestamp")),
        }
        for b in bets
        if b.get("status") in ("active", "pending", None)
    ]
    
    active_bets.sort(key=lambda b: b["executed_at"], reverse=True)
    active_bets = active_bets[:limit]
    
    log.info(f"[BETS API] Found {len(active_bets)} active bets")
    
    return {
        "active_bets": active_bets,
        "count": len(active_bets),
        "limit": limit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
