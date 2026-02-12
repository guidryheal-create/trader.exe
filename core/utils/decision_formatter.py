"""
Generalized decision formatting utilities.

Provides reusable functions for formatting decisions, extracting messages,
and building conversation structures.
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Import HTML formatter for display
try:
    from core.utils.html_formatter import (
        format_text_for_html,
        format_workflow_trace_for_html,
        format_agent_message_for_html,
        format_explanation_for_html,
    )
except ImportError:
    # Fallback if HTML formatter not available
    def format_text_for_html(text: str, max_length: Optional[int] = None) -> str:
        return text
    def format_workflow_trace_for_html(trace: List[Dict[str, Any]]) -> str:
        return str(trace)
    def format_agent_message_for_html(message: str, max_length: Optional[int] = None) -> str:
        return message
    def format_explanation_for_html(explanation: str) -> str:
        return explanation


def ensure_timestamp(decision: Dict[str, Any]) -> str:
    """
    Ensure decision has a timestamp field.
    
    Checks for timestamp, created_at, or completed_at, and adds one if missing.
    
    Args:
        decision: Decision dictionary
        
    Returns:
        ISO timestamp string
    """
    timestamp = (
        decision.get("timestamp") or
        decision.get("created_at") or
        decision.get("completed_at") or
        datetime.now(timezone.utc).isoformat()
    )
    
    # Update decision if timestamp was missing
    if "timestamp" not in decision:
        decision["timestamp"] = timestamp
    
    return timestamp


def extract_agent_messages(decision: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Extract messages by agent type from decision.
    
    Args:
        decision: Decision dictionary with messages
        
    Returns:
        Dict mapping agent type to list of messages
    """
    agents_data = {
        "trend": [],
        "fact": [],
        "fusion": [],
        "memory": [],
    }
    
    messages = decision.get("messages", [])
    
    # Also check workflow_trace for agent messages
    workflow_trace = decision.get("workflow_trace", [])
    
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "").lower()
            content = msg.get("content", "")
            
            if not content:
                continue
            
            # ✅ Hide prompts (user/system messages), show only assistant/agent replies
            # Skip user, system, and prompt messages - be more aggressive
            skip_patterns = ["user", "system", "prompt", "task", "instruction", "workflow", "canonical", "you are"]
            if any(pattern in role.lower() for pattern in skip_patterns):
                continue
            
            # Skip if content looks like a prompt (starts with "You are" or contains workflow instructions)
            content_lower_start = content.lower()[:200]
            if any(prompt_indicator in content_lower_start for prompt_indicator in [
                "you are the", "you are a", "canonical workflow", "system knowledge", 
                "execute the", "important:", "signal payload"
            ]):
                continue
            
            # Only include assistant/agent/worker messages (replies)
            # If role doesn't explicitly indicate it's a reply, check content
            if "assistant" not in role.lower() and "agent" not in role.lower() and "worker" not in role.lower():
                # Check if it's a reply by looking for common reply indicators
                is_reply = any(indicator in content.lower()[:200] for indicator in [
                    "recommend", "suggest", "analysis", "assessment", "decision", 
                    "allocation", "confidence", "sentiment", "trend", "action",
                    "based on", "according to", "the data shows", "i recommend",
                    "my analysis", "the forecast", "the signal"
                ])
                if not is_reply:
                    continue
            
            # Match agent types more broadly
            if any(keyword in role for keyword in ["trend", "chart", "dqn", "technical"]):
                agents_data["trend"].append(content)
            elif any(keyword in role for keyword in ["fact", "sentiment", "news", "research", "market_research"]):
                agents_data["fact"].append(content)
            elif any(keyword in role for keyword in ["fusion", "decision", "coordinator", "final", "review"]):
                agents_data["fusion"].append(content)
            elif any(keyword in role for keyword in ["memory", "context", "recall"]):
                agents_data["memory"].append(content)
            else:
                # If role doesn't match, try to infer from content
                content_lower = content.lower()
                if any(keyword in content_lower for keyword in ["trend", "price", "chart", "technical"]):
                    agents_data["trend"].append(content)
                elif any(keyword in content_lower for keyword in ["sentiment", "news", "fact", "research"]):
                    agents_data["fact"].append(content)
                elif any(keyword in content_lower for keyword in ["fusion", "decision", "allocation", "recommend"]):
                    agents_data["fusion"].append(content)
    
    # Also extract from workflow_trace if messages are empty
    if not any(agents_data.values()) and workflow_trace:
        for step in workflow_trace:
            if isinstance(step, dict):
                role = step.get("role", "").lower()
                # Try to get content from structured_data
                structured_data = decision.get("structured_data", {})
                if role and structured_data:
                    # Look for data related to this role
                    for key, value in structured_data.items():
                        if role in key.lower():
                            if isinstance(value, dict) and "content" in value:
                                content = value.get("content", "")
                                if content:
                                    if "trend" in role:
                                        agents_data["trend"].append(content)
                                    elif "fact" in role:
                                        agents_data["fact"].append(content)
                                    elif "fusion" in role:
                                        agents_data["fusion"].append(content)
    
    return agents_data


def extract_structured_agent_data(decision: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Extract structured data by agent type from decision.
    
    Args:
        decision: Decision dictionary with structured_data or components
        
    Returns:
        Dict mapping agent type to structured data
    """
    agents_data = {
        "trend": {"decision": None, "confidence": 0.0},
        "fact": {"sentiment": 0.0, "confidence": 0.0},
        "fusion": {"decision": None, "confidence": 0.0, "allocation": 0.0},
    }
    
    structured_data = decision.get("structured_data", {})
    components = decision.get("components", {})
    
    # Extract from structured_data
    if structured_data:
        if "trend" in structured_data:
            trend_data = structured_data["trend"]
            agents_data["trend"]["decision"] = trend_data.get("recommended_action") or trend_data.get("action")
            agents_data["trend"]["confidence"] = trend_data.get("confidence", 0.0)
        
        if "fact" in structured_data:
            fact_data = structured_data["fact"]
            agents_data["fact"]["sentiment"] = fact_data.get("sentiment_score", 0.0)
            agents_data["fact"]["confidence"] = fact_data.get("confidence", 0.0)
        
        if "fusion" in structured_data:
            fusion_data = structured_data["fusion"]
            agents_data["fusion"]["decision"] = fusion_data.get("action")
            agents_data["fusion"]["confidence"] = fusion_data.get("confidence", 0.0)
            agents_data["fusion"]["allocation"] = fusion_data.get("percent_allocation", 0.0)
    
    # Extract from components (fallback)
    if components:
        if "trend" in components:
            trend_comp = components["trend"]
            if isinstance(trend_comp, dict):
                agents_data["trend"]["decision"] = agents_data["trend"]["decision"] or trend_comp.get("recommended_action")
                agents_data["trend"]["confidence"] = agents_data["trend"]["confidence"] or trend_comp.get("confidence", 0.0)
        
        if "fact" in components:
            fact_comp = components["fact"]
            if isinstance(fact_comp, dict):
                agents_data["fact"]["sentiment"] = agents_data["fact"]["sentiment"] or fact_comp.get("sentiment_score", 0.0)
                agents_data["fact"]["confidence"] = agents_data["fact"]["confidence"] or fact_comp.get("confidence", 0.0)
        
        if "fusion" in components or decision.get("action"):
            agents_data["fusion"]["decision"] = agents_data["fusion"]["decision"] or decision.get("action")
            agents_data["fusion"]["confidence"] = agents_data["fusion"]["confidence"] or decision.get("confidence", 0.0)
            agents_data["fusion"]["allocation"] = agents_data["fusion"]["allocation"] or decision.get("percent_allocation", 0.0)
    
    return agents_data


def build_conversation_from_decision(decision: Dict[str, Any], decision_id: str) -> Dict[str, Any]:
    """
    Build a conversation structure from a decision.
    
    Args:
        decision: Decision dictionary
        decision_id: Decision ID
        
    Returns:
        Conversation dictionary with agents, messages, and final decision
    """
    # Ensure timestamp exists
    timestamp = ensure_timestamp(decision)
    
    # Extract messages by agent
    agent_messages = extract_agent_messages(decision)
    
    # If no messages found, try to extract from workflow_trace or structured_data
    if not any(agent_messages.values()):
        # Check if messages are in a different format
        messages = decision.get("messages", [])
        workflow_trace = decision.get("workflow_trace", [])
        structured_data = decision.get("structured_data", {})
        
        # Try to extract from structured_data by agent type
        for agent_type in ["trend", "fact", "fusion", "memory"]:
            if agent_type in structured_data:
                agent_data = structured_data[agent_type]
                if isinstance(agent_data, dict):
                    # Look for message or content fields
                    content = agent_data.get("message") or agent_data.get("content") or agent_data.get("explanation")
                    if content:
                        agent_messages[agent_type].append(str(content))
        
        # Try to extract from workflow_trace
        if workflow_trace and not any(agent_messages.values()):
            for step in workflow_trace:
                if isinstance(step, dict):
                    role = step.get("role", "").lower()
                    content = step.get("content") or step.get("message") or step.get("result")
                    if content:
                        if "trend" in role or "chart" in role or "dqn" in role:
                            agent_messages["trend"].append(str(content))
                        elif "fact" in role or "sentiment" in role or "news" in role:
                            agent_messages["fact"].append(str(content))
                        elif "fusion" in role or "decision" in role or "coordinator" in role:
                            agent_messages["fusion"].append(str(content))
                        elif "memory" in role:
                            agent_messages["memory"].append(str(content))
    
    # Extract structured data
    agent_structured = extract_structured_agent_data(decision)
    
    # Combine messages and structured data
    # ✅ Format messages for HTML display
    agents_data = {
        "trend": {
            "messages": [format_agent_message_for_html(msg, max_length=500) for msg in agent_messages["trend"]],
            "messages_raw": agent_messages["trend"],  # Keep raw for API compatibility
            "decision": agent_structured["trend"]["decision"],
            "confidence": agent_structured["trend"]["confidence"],
        },
        "fact": {
            "messages": [format_agent_message_for_html(msg, max_length=500) for msg in agent_messages["fact"]],
            "messages_raw": agent_messages["fact"],  # Keep raw for API compatibility
            "sentiment": agent_structured["fact"]["sentiment"],
            "confidence": agent_structured["fact"]["confidence"],
        },
        "fusion": {
            "messages": [format_agent_message_for_html(msg, max_length=500) for msg in agent_messages["fusion"]],
            "messages_raw": agent_messages["fusion"],  # Keep raw for API compatibility
            "decision": agent_structured["fusion"]["decision"],
            "confidence": agent_structured["fusion"]["confidence"],
            "allocation": agent_structured["fusion"]["allocation"],
        },
        "memory": {
            "messages": [format_agent_message_for_html(msg, max_length=500) for msg in agent_messages["memory"]],
            "messages_raw": agent_messages["memory"],  # Keep raw for API compatibility
            "context": None,
        },
    }
    
    # Build final decision with cleaned explanation (remove HTML tags)
    explanation_raw = decision.get("ai_explanation") or decision.get("rationale") or decision.get("result", "")
    
    # ✅ Clean HTML from explanation
    def clean_html_text(text: str) -> str:
        """Remove HTML tags and decode entities."""
        if not text:
            return ""
        import re
        # Remove HTML tags
        cleaned = re.sub(r'<[^>]*>', '', text)
        # Decode HTML entities
        cleaned = cleaned.replace('&#x27;', "'").replace('&quot;', '"').replace('&amp;', '&')
        cleaned = cleaned.replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
        # Remove prompt-like content
        if 'you are the' in cleaned.lower()[:200] or 'canonical workflow' in cleaned.lower()[:200]:
            return ''
        return cleaned.strip()
    
    explanation_cleaned = clean_html_text(explanation_raw)
    
    final_decision = {
        "action": decision.get("action", "HOLD"),
        "confidence": decision.get("confidence", 0.0),
        "explanation": explanation_cleaned,  # Cleaned explanation (no HTML)
        "explanation_raw": explanation_raw,  # Keep raw for API compatibility
    }
    
    # Get interval
    interval = decision.get("interval") or (decision.get("signal", {}) or {}).get("interval", "hours")
    
    # ✅ Format workflow trace for HTML display
    workflow_trace = decision.get("workflow_trace", [])
    workflow_trace_html = format_workflow_trace_for_html(workflow_trace) if workflow_trace else ""
    
    # Extract enhanced logging fields
    title = decision.get("title")
    user_explanation = decision.get("user_explanation") or decision.get("message", "")  # Fallback to message if user_explanation not present
    message = decision.get("message", "")
    tools_used = decision.get("tools_used", [])
    agents_involved = decision.get("agents_involved", [])
    citations = decision.get("citations", [])
    decision_metadata = decision.get("decision_metadata", {})
    
    # If not in decision directly, try to extract from structured_data or metadata
    if not title and decision.get("structured_data"):
        title = decision.get("structured_data", {}).get("title")
    if not user_explanation and decision.get("structured_data"):
        user_explanation = decision.get("structured_data", {}).get("user_explanation") or decision.get("structured_data", {}).get("message", "")
    if not message and decision.get("structured_data"):
        message = decision.get("structured_data", {}).get("message", "")
    if not tools_used and decision.get("structured_data"):
        tools_used = decision.get("structured_data", {}).get("tools_used", [])
    if not agents_involved and decision.get("structured_data"):
        agents_involved = decision.get("structured_data", {}).get("agents_involved", [])
    if not citations and decision.get("structured_data"):
        citations = decision.get("structured_data", {}).get("citations", [])
    if not decision_metadata and decision.get("structured_data"):
        decision_metadata = decision.get("structured_data", {}).get("decision_metadata", {})
    
    conversation = {
        "decision_id": decision_id,
        "ticker": decision.get("ticker", ""),
        "timestamp": timestamp,
        "interval": interval,
        "agents": agents_data,
        "final_decision": final_decision,
        "status": decision.get("status", "completed"),
        "structured_data": decision.get("structured_data", {}),
        "workflow_trace": workflow_trace,  # Raw workflow trace
        "workflow_trace_html": workflow_trace_html,  # HTML-formatted workflow trace
        "agentic": decision.get("agentic", True),
        # Enhanced logging fields
        "title": title,
        "user_explanation": user_explanation,
        "message": message,
        "tools_used": tools_used if isinstance(tools_used, list) else [],
        "agents_involved": agents_involved if isinstance(agents_involved, list) else [],
        "citations": citations if isinstance(citations, list) else [],
        "decision_metadata": decision_metadata if isinstance(decision_metadata, dict) else {},
    }
    
    return conversation


def is_valid_agentic_decision(decision: Dict[str, Any]) -> bool:
    """
    Check if a decision is a valid agentic decision.
    
    Args:
        decision: Decision dictionary
        
    Returns:
        True if valid agentic decision
    """
    status = decision.get("status", "completed")
    agentic = decision.get("agentic", True)
    
    # Skip degraded or failed
    if status in ["degraded", "failed"]:
        return False
    
    # Skip non-agentic
    if agentic is False:
        return False
    
    # Check for actual agent content
    messages = decision.get("messages", [])
    workflow_trace = decision.get("workflow_trace", [])
    structured_data = decision.get("structured_data", {})
    
    # Must have some agent content
    if not messages and not workflow_trace and not structured_data:
        # Only skip if it's clearly degraded (has error field)
        if decision.get("error") or "unavailable" in str(decision.get("result", "")).lower():
            return False
    
    return True

