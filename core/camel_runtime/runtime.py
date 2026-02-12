"""
CamelTradingRuntime orchestrates society, memory, and task execution.

This runtime is the single integration point used by the orchestrator,
pipelines, and API entrypoints.  It exposes convenience methods for
processing workforce tasks, running ad-hoc prompts, and marshalling
decision traces.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.logging import log
from core.config import settings
from core.redis_client import redis_client
from core.camel_runtime.societies import society_factory
from core.models import AgentSignal


class CamelTradingRuntime:
    """Singleton-style runtime wrapper."""

    _instance: Optional["CamelTradingRuntime"] = None
    _initialise_lock = asyncio.Lock()

    def __init__(self) -> None:
        self._workforce = None
        self._runtime_lock = asyncio.Lock()

    @classmethod
    async def instance(cls) -> "CamelTradingRuntime":
        if cls._instance is None:
            async with cls._initialise_lock:
                if cls._instance is None:
                    cls._instance = CamelTradingRuntime()
                    await cls._instance._initialise()
        return cls._instance

    async def _initialise(self) -> None:
        """Initialise the workforce society and ensure Redis connection."""
        try:
            log.info("Initializing CAMEL workforce...")
            self._workforce = await society_factory.build()
            log.info("CAMEL workforce initialized successfully")
        except Exception as exc:  # pragma: no cover - retry system will handle
            self._workforce = None
            # ✅ Enhanced error logging to help diagnose workforce initialization failures
            error_type = type(exc).__name__
            error_msg = str(exc)
            error_traceback = None
            try:
                import traceback
                error_traceback = traceback.format_exc()
            except Exception:
                pass
            
            log.error(
                "❌ FAILED to initialise CAMEL workforce (%s: %s).\n"
                "Workforce will be retried via retry system. Signal processing will raise RuntimeError until workforce is available.\n"
                "Full traceback:\n%s",
                error_type,
                error_msg,
                error_traceback or "Unable to capture traceback",
                exc_info=True
            )
            # ✅ No fallback mode - raise error to trigger retry system
            raise RuntimeError(
                f"Failed to initialize CAMEL workforce: {error_type}: {error_msg}. "
                "Workforce will be retried via retry system."
            ) from exc
        if not redis_client.redis:
            await redis_client.connect()
        log.info("CamelTradingRuntime initialised successfully")

    async def ensure_ready(self) -> bool:
        """Attempt to recover the workforce using retry system only."""
        if self._workforce is not None:
            return True

        async with self._runtime_lock:
            if self._workforce is not None:
                return True

            # Retry initialization with exponential backoff (retry system only)
            max_retries = 3
            retry_delay = 1.0
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    log.info(f"Attempting to recover CAMEL workforce (attempt {attempt + 1}/{max_retries})...")
                    workforce = await society_factory.build()
                    self._workforce = workforce
                    log.info("CamelTradingRuntime recovered successfully")
                    return True
                except Exception as exc:
                    last_error = exc
                    log.warning(
                        f"CAMEL workforce recovery attempt {attempt + 1}/{max_retries} failed: {type(exc).__name__}: {exc}"
                    )
                    if attempt < max_retries - 1:
                        import asyncio
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        retry_delay *= 1.5  # Exponential backoff
            
            # All retries failed
            if last_error:
                log.error(
                    f"Failed to recover CAMEL workforce after {max_retries} attempts: {type(last_error).__name__}: {last_error}",
                    exc_info=True
                )
            return False

    async def get_workforce(self) -> Any:
        """Return the active Workforce instance, initializing if needed."""
        if self._workforce is None:
            await self.ensure_ready()
        if self._workforce is None:
            raise RuntimeError("Workforce is not available")
        return self._workforce


    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _format_decision(self, decision_id: str, signal: Dict[str, Any], response: Any) -> Dict[str, Any]:
        """Serialise the workforce response into the UI-friendly schema.
        
        Extracts the full society workflow result, including:
        - All messages from coordinator, task agent, and workers
        - Structured data from parsed responses
        - Workflow trace information
        """
        agent_signal = AgentSignal.parse_obj(signal)
        result_text = ""
        messages = []
        workflow_trace = []
        structured_data = {}

        if isinstance(response, dict):
            result_text = response.get("text") or response.get("result") or ""
            messages = response.get("messages", [])
            workflow_trace = response.get("workflow_trace", [])
            # ✅ Safely extract structured_data - handle KeyError for return_json_response
            structured_data = {}
            try:
                # ✅ Get structured_data safely - handle missing keys
                raw_structured = response.get("structured_data", {})
                if isinstance(raw_structured, dict):
                    structured_data = raw_structured.copy()
                    # ✅ Handle return_json_response wrapper if present
                    if "return_json_response" in structured_data:
                        return_json_data = structured_data.get("return_json_response")
                        if isinstance(return_json_data, dict):
                            # Merge nested data into structured_data
                            structured_data = {**structured_data, **return_json_data}
                            # Remove wrapper key
                            structured_data.pop("return_json_response", None)
                        elif return_json_data is not None:
                            # If return_json_response is not a dict, keep it as-is
                            log.debug(f"return_json_response is not a dict: {type(return_json_data)}")
                elif raw_structured:
                    # If structured_data is not a dict, wrap it
                    structured_data = {"data": raw_structured}
            except (KeyError, TypeError, AttributeError) as e:
                log.warning(f"Failed to extract structured_data from response: {e}")
                structured_data = {}
        elif hasattr(response, "msgs"):
            # Extract all messages from the society workflow
            all_messages = response.msgs or []
            messages = []
            
            for msg in all_messages:
                content = getattr(msg, "content", "") or ""
                role = getattr(msg, "role_name", getattr(msg, "role", "unknown"))
                msg_dict = {
                    "role": role,
                    "content": content,
                    "timestamp": getattr(msg, "created_at", None) or datetime.now(timezone.utc).isoformat(),
                }
                
                # Extract parsed/structured data if available
                parsed_obj = getattr(msg, "parsed", None)
                if parsed_obj:
                    msg_dict["parsed"] = str(parsed_obj)
                    # Try to extract structured data from parsed object
                    try:
                        if hasattr(parsed_obj, "model_dump"):
                            parsed_dict = parsed_obj.model_dump()
                        elif isinstance(parsed_obj, dict):
                            parsed_dict = parsed_obj
                        else:
                            # Try to convert to dict if possible
                            try:
                                parsed_dict = dict(parsed_obj) if hasattr(parsed_obj, '__dict__') else {"value": str(parsed_obj)}
                            except Exception:
                                parsed_dict = {"value": str(parsed_obj)}
                        
                        # ✅ Handle return_json_response wrapper if present
                        if isinstance(parsed_dict, dict):
                            # Check if return_json_response exists and extract nested data
                            if "return_json_response" in parsed_dict:
                                return_json_data = parsed_dict.get("return_json_response")
                                if isinstance(return_json_data, dict):
                                    # Use nested data instead of wrapper
                                    structured_data[f"{role}_parsed"] = return_json_data
                                elif return_json_data is not None:
                                    # If return_json_response is not a dict, wrap it
                                    structured_data[f"{role}_parsed"] = {"return_json_response": return_json_data}
                                else:
                                    # return_json_response is None, use original dict
                                    structured_data[f"{role}_parsed"] = parsed_dict
                            else:
                                structured_data[f"{role}_parsed"] = parsed_dict
                        else:
                            structured_data[f"{role}_parsed"] = {"value": str(parsed_dict)}
                    except (KeyError, AttributeError, TypeError) as e:
                        # ✅ Handle KeyError for return_json_response and other extraction errors
                        if "return_json_response" in str(e):
                            log.debug(f"return_json_response KeyError in parsed object (handled): {e}")
                            # Try to extract what we can
                            try:
                                structured_data[f"{role}_parsed"] = {"raw": str(parsed_obj)}
                            except Exception:
                                pass
                        else:
                            log.debug(f"Failed to extract structured data from parsed object: {e}")
                    except Exception as e:
                        log.debug(f"Unexpected error extracting structured data: {e}")
                
                messages.append(msg_dict)
                
                # Build workflow trace
                if role not in [t.get("role") for t in workflow_trace]:
                    workflow_trace.append({
                        "role": role,
                        "step": len(workflow_trace) + 1,
                        "has_content": bool(content),
                        "has_parsed": parsed_obj is not None,
                    })
            
            # Result text is the coordinator's final decision or last meaningful message
            coordinator_msgs = [m for m in messages if m.get("role", "").lower() in ["coordinator", "task"]]
            if coordinator_msgs:
                result_text = coordinator_msgs[-1].get("content", "")
            elif messages:
                result_text = messages[-1].get("content", "")
        else:
            result_text = str(response)

        payload = {
            "decision_id": decision_id,
            "status": "completed",
            "ticker": agent_signal.ticker,
            "action": agent_signal.action.name if agent_signal.action else None,
            "confidence": agent_signal.confidence,
            "result": result_text or "[no agent response]",
            "timestamp": datetime.now(timezone.utc).isoformat(),  # ✅ Always include timestamp
            "interval": signal.get("interval", "hours"),  # ✅ Include interval from signal
            "messages": messages,
            "workflow_trace": workflow_trace,
            "structured_data": structured_data,
            "signal": signal,
        }
        payload["agentic"] = self._workforce is not None
        
        # ✅ Extract ai_explanation from signal data if available (from fusion pipeline)
        signal_data = signal.get("data", {}) if isinstance(signal, dict) else {}
        ai_explanation_from_signal = None
        if isinstance(signal_data, dict):
            ai_explanation_from_signal = signal_data.get("ai_explanation")
            if not ai_explanation_from_signal:
                # Try nested path
                components = signal_data.get("components", {})
                if isinstance(components, dict):
                    fusion_data = components.get("fusion", {})
                    if isinstance(fusion_data, dict):
                        ai_explanation_from_signal = fusion_data.get("ai_explanation")
        
        # ✅ Prefer ai_explanation from signal, fallback to result_text
        payload["ai_explanation"] = (
            ai_explanation_from_signal.strip() if ai_explanation_from_signal
            else result_text.strip() if result_text
            else f"Aggregated workforce decision for {agent_signal.ticker or 'N/A'}."
        )
        
        log.info(
            f"✅ Formatted decision {decision_id}: {len(messages)} messages, "
            f"{len(workflow_trace)} workflow steps, agentic={payload['agentic']}, "
            f"ticker={payload.get('ticker', 'N/A')}, action={payload.get('action', 'N/A')}"
        )
        
        # ✅ Ensure messages are properly formatted for logging
        if messages:
            log.info(f"✅ Decision {decision_id} has {len(messages)} chat messages for logging")
            # Log sample message structure
            if messages[0]:
                sample_msg = messages[0]
                log.debug(f"   Sample message: role={sample_msg.get('role', 'unknown')}, "
                         f"content_length={len(sample_msg.get('content', ''))}")
        else:
            log.warning(f"⚠️  Decision {decision_id} has no messages extracted from workforce response")
        
        # ✅ Save agentic conversation to Redis for logging endpoints
        try:
            conversation_key = f"agentic:conversation:{decision_id}"
            conversation_data = {
                "decision_id": decision_id,
                "ticker": signal.get("ticker", "unknown"),
                "interval": signal.get("interval", "unknown"),
                "strategy": signal.get("strategy", "unknown"),
                "messages": messages,
                "workflow_trace": workflow_trace,
                "structured_data": structured_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agentic": True,
            }
            # Save to Redis (async, non-blocking)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._async_save_conversation(conversation_key, conversation_data))
                else:
                    loop.run_until_complete(self._async_save_conversation(conversation_key, conversation_data))
            except RuntimeError:
                log.debug(f"Could not save conversation to Redis (no event loop)")
        except Exception as e:
            log.warning(f"Failed to save conversation for logging: {e}", exc_info=True)
        
        # ✅ Record signal to memory for review pipeline feedback (schedule as task)
        # This allows review pipeline to collect metrics for weight optimization
        try:
            signal_record = {
                "agent_type": agent_signal.agent_type.value if hasattr(agent_signal.agent_type, 'value') else str(agent_signal.agent_type),
                "signal_type": agent_signal.signal_type.value if hasattr(agent_signal.signal_type, 'value') else str(agent_signal.signal_type),
                "ticker": agent_signal.ticker,
                "action": agent_signal.action.name if agent_signal.action else None,
                "confidence": agent_signal.confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "decision_id": decision_id,
                "agentic": payload["agentic"],
                "data": signal,
            }
            # Schedule async task to record signal (non-blocking)
            # _format_decision is not async, so we schedule the async operation
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._async_record_signal(signal_record))
                else:
                    loop.run_until_complete(self._async_record_signal(signal_record))
            except RuntimeError:
                # No event loop available, skip recording
                log.debug(f"Could not record signal to memory (no event loop)")
        except Exception as e:
            log.warning(f"Failed to schedule signal recording to memory: {e}", exc_info=True)

        return payload
    
    async def _async_record_signal(self, signal_record: dict) -> None:
        """Async helper to record signal to memory:signals."""
        try:
            await redis_client.lpush("memory:signals", json.dumps(signal_record))
            await redis_client.ltrim("memory:signals", 0, 999)  # Keep last 1000
            log.debug(f"Recorded signal to memory: {signal_record.get('agent_type')} for {signal_record.get('ticker')}")
        except Exception as e:
            log.warning(f"Failed to record signal to memory: {e}", exc_info=True)
    
    async def _async_save_conversation(self, conversation_key: str, conversation_data: dict) -> None:
        """Async helper to save agentic conversation to Redis for logging endpoints."""
        try:
            from core.redis_client import redis_client
            # Save with 7-day TTL for conversation logs
            # Use redis_client.redis.setex (Redis client method)
            await redis_client.redis.setex(
                conversation_key,
                7 * 24 * 60 * 60,  # 7 days
                json.dumps(conversation_data, default=str)
            )
            # Also add to conversation list for easy retrieval
            await redis_client.redis.lpush("agentic:conversations:list", conversation_key)
            await redis_client.redis.ltrim("agentic:conversations:list", 0, 9999)  # Keep last 10000
            log.info(f"✅ Saved conversation {conversation_key} to Redis: {len(conversation_data.get('messages', []))} messages")
        except Exception as e:
            log.warning(f"Failed to save conversation to Redis: {e}", exc_info=True)




# ✅ REMOVED: process_signal and run_task factory helpers
# Use DailyProcess and other pipeline modules directly instead


