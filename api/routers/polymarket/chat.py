"""Polymarket router package - CAMEL chat agent interface."""
from fastapi import APIRouter, Query

from api.models.polymarket import ChatRequest, ChatResponse
from api.services.polymarket.logging_service import logging_service
from api.services.polymarket.chat_service import chat_service
from core.clients.redis_client import RedisClient
from core.memory.workspace_memory import WorkspaceMemory
from core.logging import log

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(chat_request: ChatRequest) -> ChatResponse:
    """
    Chat with CAMEL trading agent
    
    Args:
        chat_request: message, context (optional)
    
    Returns:
        Agent response with analysis and recommendations
    """
    message = chat_request.message
    context_id = chat_request.context or "polymarket"
    chat_service.add_message("user", message)

    redis_client = RedisClient()
    workspace = WorkspaceMemory(redis_client)
    try:
        await redis_client.connect()
        await workspace.add_chat_message(context_id, "user", message)
    except Exception as exc:
        log.warning(f"[CHAT] Workspace memory not available: {exc}")

    response_text = f"ACK: {message}"
    analysis = None
    recommendations = []

    try:
        from camel.tasks import Task
        from core.camel_runtime.societies import TradingWorkforceSociety

        society = TradingWorkforceSociety()
        workforce = await society.build()
        task = Task(
            content=(
                "You are a Polymarket assistant. Answer the user briefly and clearly.\n\n"
                f"User message: {message}\n"
                f"Context ID: {context_id}\n"
            )
        )

        result = await workforce.process_task(task)
        # workforce.get_workforce_log_tree() # Returns an ASCII tree representation of the task hierarchy and worker status.
        # workforce.get_pending_tasks() # Get current pending tasks for human review.
        # workforce.get_completed_tasks() # Get completed tasks.
        # workforce.get_workforce_kpis() # Returns a dictionary of key performance indicators.
        # workforce.to_mcp() 
        """
        def to_mcp(
            name: str = "CAMEL-Workforce",
            description: str = "A workforce system using the CAM" "multi-agent collaboration.",
            dependencies: List[str] | None = None,
            host: str = "localhost",
            port: int = 8001
        ) -> FastMCP[Any]
        Expose this Workforce as an MCP server.

        Args
        name : str
        Name of the MCP server. (default: CAMEL-Workforce)
        """
        #workforce.stop_gracefully() # Request workforce to finish current in-flight work then halt.



        if isinstance(result, dict):
            response_text = result.get("response") or result.get("answer") or result.get("content") or response_text
            analysis = result.get("analysis")
            recommendations = result.get("recommendations") or []
        elif isinstance(result, str):
            response_text = result
    except Exception as exc:
        log.warning(f"[CHAT] CAMEL agent unavailable, using stub: {exc}")

    chat_service.add_message("agent", response_text)
    try:
        await workspace.add_chat_message(context_id, "assistant", response_text)
    except Exception:
        pass

    logging_service.log_event("INFO", "Chat message processed", {"context": context_id})
    return ChatResponse(response=response_text, analysis=analysis, recommendations=recommendations)


@router.get("/chat/history")
async def get_chat_history(limit: int = Query(50, ge=1, le=500), context: str | None = None):
    """
    Get chat conversation history
    
    Args:
        limit: Number of recent messages
    
    Returns:
        Chat history with all exchanges
    """
    if context:
        redis_client = RedisClient()
        workspace = WorkspaceMemory(redis_client)
        try:
            await redis_client.connect()
            messages = await workspace.get_chat_history(context)
            return {"messages": messages, "limit": limit, "context": context}
        except Exception:
            pass
    return {"messages": chat_service.list_messages(limit=limit), "limit": limit}


@router.delete("/chat/history")
async def clear_chat_history(context: str | None = None):
    """
    Clear chat history
    
    Returns:
        Confirmation of history cleared
    """
    chat_service.clear()
    if context:
        redis_client = RedisClient()
        workspace = WorkspaceMemory(redis_client)
        try:
            await redis_client.connect()
            await workspace.clear_chat_history(context)
        except Exception:
            pass
    return {"cleared": True}


@router.get("/chat/status")
async def get_agent_status():
    """
    Get current CAMEL agent status
    
    Returns:
        Agent status, models loaded, capabilities
    """
    return {"status": "ready", "capabilities": ["camel-agent", "workspace-memory"], "model": "configured"}


@router.post("/chat/analyze/{market_id}")
async def analyze_with_agent(market_id: str, context: str = "neutral"):
    """
    Ask agent to analyze a specific Polymarket market
    
    Args:
        market_id: Polymarket market ID
        context: Analysis context (bullish, bearish, neutral)
    
    Returns:
        Agent analysis with reasoning
    """
    message = f"Analyze market {market_id} with context={context}"
    chat_service.add_message("user", message)
    response = f"Analysis stub for {market_id} ({context})."
    chat_service.add_message("agent", response)
    return {"market_id": market_id, "analysis": response}




@router.post("/chat/rebalance")
async def ask_rebalance_recommendation(strategy: str = "auto"):
    """
    Ask agent for rebalancing recommendation
    
    Args:
        strategy: Strategy to consider
    
    Returns:
        Agent recommendation with rationale
    """
    message = f"Rebalance recommendation for strategy={strategy}"
    chat_service.add_message("user", message)
    response = f"Rebalance recommendation stub for {strategy}."
    chat_service.add_message("agent", response)
    return {"strategy": strategy, "recommendation": response}
