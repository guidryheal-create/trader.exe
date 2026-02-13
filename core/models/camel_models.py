"""
CAMEL Model Configuration Factory

Supports multiple model providers: OpenAI, Gemini, and local models.
"""
from pathlib import Path
import sys
from typing import Optional, Dict, Any, Callable, Tuple
import httpx

# Lazy import to avoid circular dependencies
_settings = None
_log = None


def _get_settings():
    """Get settings lazily."""
    global _settings
    if _settings is None:
        from core.settings.config import settings as s
        _settings = s
    return _settings


def _get_log():
    """Get logger lazily."""
    global _log
    if _log is None:
        from core.logging import log as l
        _log = l
    return _log

# Allow bundling the upstream CAMEL repository alongside this project
_local_camel_repo = Path(__file__).resolve().parents[2] / "camel"
if _local_camel_repo.exists():
    repo_path = str(_local_camel_repo)
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)

try:
    from camel.types import ModelType, ModelPlatformType
    from camel.models import ModelFactory
    from camel.configs import GeminiConfig
    CAMEL_AVAILABLE = True
except ImportError:
    CAMEL_AVAILABLE = False
    _get_log().warning("CAMEL-AI not available. Install with: pip install camel-ai")
    GeminiConfig = None
    OpenRouterConfig = None
    # Define stubs for type hints
    ModelType = Any
    ModelPlatformType = Any
    ModelFactory = None
    def _patch_search_toolkit() -> None:
        """Patch SearchToolkit to ensure all tools are wrapped as FunctionTool instances."""
        try:
            from camel.toolkits import FunctionTool  # type: ignore
            from camel.toolkits.search_toolkit import SearchToolkit  # type: ignore
        except ImportError:
            return

        # Patch get_tools method
        original_get_tools = getattr(SearchToolkit, "get_tools", None)
        if not callable(original_get_tools):
            return
        if getattr(SearchToolkit.get_tools, "_ats_patched", False):  # type: ignore[attr-defined]
            return

        def _patched_get_tools(self, *args, **kwargs):
            """Wrap all SearchToolkit tools as FunctionTool instances."""
            tools = original_get_tools(self, *args, **kwargs)
            wrapped = []
            for tool in tools or []:
                if isinstance(tool, FunctionTool):
                    wrapped.append(tool)
                else:
                    try:
                        # Handle bound methods - extract the function
                        if hasattr(tool, "__func__"):
                            fn = tool.__func__
                        elif hasattr(tool, "__call__"):
                            fn = tool
                        else:
                            fn = tool
                        
                        wrapped_tool = FunctionTool(fn)
                        wrapped.append(wrapped_tool)
                    except Exception as exc:  # pragma: no cover - defensive
                        _get_log().warning("Failed to wrap search toolkit tool %s: %s", tool, exc)
            return wrapped

        _patched_get_tools._ats_patched = True  # type: ignore[attr-defined]
        SearchToolkit.get_tools = _patched_get_tools  # type: ignore[assignment]
        _get_log().debug("Patched CAMEL SearchToolkit.get_tools to return FunctionTool instances")

    _patch_search_toolkit()


class CamelModelFactory:
    """Factory for creating CAMEL-compatible model instances."""
    
    _model_cache: Dict[str, Any] = {}
    _fallback_notice_logged: bool = False
    _gemini_status_checked: bool = False
    _gemini_key_valid: bool = False
    
    @classmethod
    def get_model_type(
        cls, model_name: str, platform_hint: Optional[str] = None
    ) -> Optional[ModelType]:
        """Convert model name string to CAMEL ModelType enum."""
        if not CAMEL_AVAILABLE:
            return None
        
        _, normalized_name, _ = cls._parse_model_identifier(model_name, platform_hint)

        normalized_key = normalized_name.replace("/", "_").replace("-", "_")

        model_map: Dict[str, ModelType] = {}

        base_map = {
            "gpt-5.1-mini": "GPT_5_1_MINI",
            "gpt-4o-mini": "GPT_4O_MINI",  # legacy fallback
            "gpt-4.1-mini": "GPT_4O_MINI",  # ✅ Rate limit fallback model
            "gpt-4o": "GPT_4O",
            "gpt-4-turbo": "GPT_4_TURBO",
            "gpt-3.5-turbo": "GPT_3_5_TURBO",
            "claude-3-opus": "CLAUDE_3_OPUS",
            "claude-3-sonnet": "CLAUDE_3_SONNET",
            "claude-3-haiku": "CLAUDE_3_HAIKU",
            "gemini-pro": "GEMINI_1_5_PRO",
            "gemini-1.5-pro": "GEMINI_1_5_PRO",
            "gemini-1.5-flash": "GEMINI_1_5_FLASH",
            "gemini-2.0-flash": "GEMINI_2_0_FLASH",
            "gemini-2.5-pro": "GEMINI_2_5_PRO",
            "gemini-2.5-flash": "GEMINI_2_5_FLASH",
            "gemini-2.0-flash-thinking-exp": "GEMINI_2_0_FLASH_THINKING_EXP",
            "gemini-2.0-flash-lite": "GEMINI_2_0_FLASH_LITE",
            "gemini-pro-vision": "GEMINI_1_5_PRO",
        }

        for name, attr in base_map.items():
            enum_value = getattr(ModelType, attr, None)
            if enum_value:
                model_map[name] = enum_value

        candidate_keys = [
            normalized_name,
            normalized_key,
        ]

        for key in candidate_keys:
            if key in model_map:
                return model_map[key]

        return None
    
    @classmethod
    def create_model(
        cls,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Create a CAMEL model instance.
        
        Args:
            model_name: Model name (defaults to _get_settings().camel_default_model)
            api_key: API key for the model (defaults to OpenAI key from settings)
            **kwargs: Additional model-specific parameters
            
        Returns:
            CAMEL model instance
        """
        if not CAMEL_AVAILABLE:
            raise ImportError("CAMEL-AI is not installed. Install with: pip install camel-ai")
        
        resolved_name, base_model_name, platform_hint = cls._resolve_model_name(
            model_name or _get_settings().camel_default_model
        )
        cache_key = f"{resolved_name}_{api_key or 'default'}"
        
        # Return cached model if available
        if cache_key in cls._model_cache:
            return cls._model_cache[cache_key]
        
        model_type = cls.get_model_type(base_model_name, platform_hint)
        if not model_type:
            _get_log().warning("Unknown model type: %s, using default", resolved_name)
            model_type = ModelType.GPT_4O_MINI
        
        # Determine API key based on model type
        if not api_key:
            api_key = cls._resolve_api_key(resolved_name, base_model_name, platform_hint)
            if not api_key:
                raise ValueError(
                    f"No API key configured for resolved model '{resolved_name}'"
                )
        
        def _build_model(
            selected_model_type: ModelType,
            selected_platform: ModelPlatformType,
            selected_key: str,
            selected_config: Optional[Dict[str, Any]] = None,
            selected_url: Optional[str] = None,
        ):
            return ModelFactory.create(
                model_platform=selected_platform,
                model_type=selected_model_type,
                api_key=selected_key,
                model_config_dict=dict(selected_config or {}),
                url=selected_url,
            )

        try:
            model_platform = cls._resolve_platform(resolved_name, base_model_name, platform_hint)
            model_config = kwargs or cls._default_model_config(
                model_platform, platform_hint
            )
            model_url = cls._resolve_base_url(model_platform, platform_hint)

            if model_platform == ModelPlatformType.GEMINI:
                if not cls._ensure_gemini_available():
                    _get_log().warning(
                        "Gemini API unavailable; falling back to '%s' for CAMEL model.",
                        _get_settings().camel_fallback_model,
                    )
                    fallback_name = _get_settings().camel_fallback_model or "gpt-5.1-mini"
                    (
                        fallback_api_model,
                        fallback_base_model,
                        fallback_hint,
                    ) = cls._parse_model_identifier(fallback_name)
                    fallback_key = cls._resolve_api_key(
                        fallback_api_model, fallback_base_model, fallback_hint
                    )
                    if not fallback_key:
                        return None
                    fallback_platform = cls._resolve_platform(
                        fallback_api_model, fallback_base_model, fallback_hint
                    )
                    fallback_model_type = (
                        cls.get_model_type(fallback_base_model, fallback_hint)
                        or ModelType.GPT_4O_MINI
                    )
                    fallback_config = cls._default_model_config(
                        fallback_platform, fallback_hint
                    )
                    fallback_url = cls._resolve_base_url(fallback_platform, fallback_hint)
                    model = _build_model(
                        fallback_model_type,
                        fallback_platform,
                        fallback_key,
                        fallback_config,
                        fallback_url,
                    )
                    cls._model_cache[cache_key] = model
                    return model

            model = _build_model(
                model_type,
                model_platform,
                api_key,
                model_config,
                model_url,
            )

            cls._model_cache[cache_key] = model
            _get_log().info("Created CAMEL model: %s", resolved_name)
            return model

        except Exception as e:
            error_msg = str(e)
            _get_log().error("Failed to create model %s: %s", resolved_name, error_msg)

            fallback = cls._attempt_immediate_fallback(
                cache_key=cache_key,
                build_fn=_build_model,
                original_error=error_msg,
                model_name=resolved_name,
            )
            if fallback:
                return fallback

            raise

    @classmethod
    def create_coordinator_model(cls) -> Any:
        """Create model for coordinator agents in CAMEL workforce."""
        # ✅ Use gpt-5.1-mini for lower cost and latest behaviours
        model_name = _get_settings().camel_coordinator_model or _get_settings().camel_primary_model or "openai/gpt-5.1-mini"
        if model_name == "auto":
            model_name = _get_settings().camel_primary_model or "openai/gpt-5.1-mini"
        api_model, base_model, hint = cls._parse_model_identifier(model_name)
        api_key = cls._resolve_api_key(api_model, base_model, hint)
        return cls.create_model(model_name=model_name, api_key=api_key)

    @classmethod
    def create_task_model(cls) -> Any:
        """Create model for task decomposition agents."""
        # ✅ Use gpt-5.1-mini for lower cost and latest behaviours
        model_name = _get_settings().camel_task_model or _get_settings().camel_primary_model or "openai/gpt-5.1-mini"
        if model_name == "auto":
            model_name = _get_settings().camel_primary_model or "openai/gpt-5.1-mini"
        api_model, base_model, hint = cls._parse_model_identifier(model_name)
        api_key = cls._resolve_api_key(api_model, base_model, hint)
        return cls.create_model(model_name=model_name, api_key=api_key)

    @classmethod
    def create_worker_model(cls) -> Any:
        """Create model for workforce workers."""
        # ✅ Use gpt-5.1-mini for lower cost and latest behaviours
        model_name = _get_settings().camel_worker_model or _get_settings().camel_primary_model or "openai/gpt-5.1-mini"
        if model_name == "auto":
            model_name = _get_settings().camel_primary_model or "openai/gpt-5.1-mini"
        api_model, base_model, hint = cls._parse_model_identifier(model_name)
        api_key = cls._resolve_api_key(api_model, base_model, hint)
        return cls.create_model(model_name=model_name, api_key=api_key)

    @classmethod
    def clear_cache(cls) -> None:
        cls._model_cache.clear()
        _get_log().info("CAMEL model cache cleared")

    @classmethod
    def _resolve_model_name(
        cls, requested: str
    ) -> Tuple[str, str, Optional[str]]:
        candidate = (requested or "").strip() or "auto"
        if candidate.lower() != "auto":
            return cls._parse_model_identifier(candidate)

        priorities = []
        primary = _get_settings().camel_primary_model.strip() if _get_settings().camel_primary_model else ""
        fallback = _get_settings().camel_fallback_model.strip() if _get_settings().camel_fallback_model else ""

        # ✅ Always prefer OpenAI (GPT-4) over Gemini
        # User wants to use OpenAI API key, not Gemini
        if primary and not _get_settings().camel_prefer_gemini:
            priorities.append(primary)
            if fallback:
                priorities.append(fallback)
        elif fallback:
            priorities.append(fallback)
            if primary:
                priorities.append(primary)
        else:
            # Default to gpt-5.1-mini for lower cost if nothing configured
            priorities.append("gpt-5.1-mini")

        for name in priorities:
            api_model, base_model, hint = cls._parse_model_identifier(name)
            lowered = base_model.lower()

            if hint == "gemini" and not _get_settings().gemini_api_key:
                continue
            if hint == "openai" and not _get_settings().openai_api_key:
                continue
            return api_model, base_model, hint

        raise ValueError(
            "No CAMEL model can be resolved. Configure GEMINI_API_KEY or OPENAI_API_KEY (or disable camel_prefer_gemini)."
        )

    @classmethod
    def _resolve_api_key(
        cls,
        api_model: str,
        base_model: str,
        platform_hint: Optional[str] = None,
    ) -> Optional[str]:
        hint = platform_hint
        lowered_base = base_model.lower()

        if hint is None:
            _, _, hint = cls._parse_model_identifier(api_model, platform_hint)

        if hint == "gemini":
            return _get_settings().gemini_api_key

        # Default to OpenAI
        return _get_settings().openai_api_key

    @classmethod
    def _resolve_platform(
        cls,
        api_model: str,
        base_model: str,
        platform_hint: Optional[str] = None,
    ) -> ModelPlatformType:
        hint = platform_hint

        if hint is None:
            _, _, hint = cls._parse_model_identifier(api_model, platform_hint)

        if hint == "gemini":
            return ModelPlatformType.GEMINI
        if hint == "anthropic":
            return ModelPlatformType.ANTHROPIC
        return ModelPlatformType.OPENAI

    @classmethod
    def _attempt_immediate_fallback(
        cls,
        cache_key: str,
        build_fn: Callable[
            [ModelType, ModelPlatformType, str, Optional[Dict[str, Any]], Optional[str]],
            Any,
        ],
        original_error: str,
        model_name: str,
    ) -> Optional[Any]:
        # ✅ Check if error is rate limit related - use gpt-4.1-mini as fallback
        error_lower = original_error.lower()
        is_rate_limit = (
            "rate limit" in error_lower or 
            "429" in error_lower or 
            "rate_limit" in error_lower or
            "quota" in error_lower or
            "too many requests" in error_lower
        )
        
        # ✅ Use gpt-4.1-mini for rate limit errors, otherwise use configured fallback
        if is_rate_limit:
            fallback_name = "openai/gpt-4.1-mini"
            _get_log().info(
                "Rate limit detected for '%s'; switching to gpt-4.1-mini as fallback",
                model_name
            )
        else:
            fallback_name = _get_settings().camel_fallback_model
            if not fallback_name:
                return None

        try:
            (
                fallback_api_model,
                fallback_base_model,
                fallback_hint,
            ) = cls._parse_model_identifier(fallback_name)
            fallback_key = cls._resolve_api_key(
                fallback_api_model, fallback_base_model, fallback_hint
            )
            if not fallback_key:
                return None

            fallback_platform = cls._resolve_platform(
                fallback_api_model, fallback_base_model, fallback_hint
            )
            fallback_model_type = (
                cls.get_model_type(fallback_base_model, fallback_hint)
                or ModelType.GPT_4O_MINI
            )
            fallback_config = cls._default_model_config(
                fallback_platform, fallback_hint
            )
            fallback_url = cls._resolve_base_url(fallback_platform, fallback_hint)

            fallback_model = build_fn(
                fallback_model_type,
                fallback_platform,
                fallback_key,
                fallback_config,
                fallback_url,
            )
            cls._model_cache[f"fallback_{cache_key}"] = fallback_model
            _get_log().warning(
                "Primary model '%s' unavailable (%s); using fallback '%s'",
                model_name,
                original_error,
                fallback_name,
            )
            cls._fallback_notice_logged = True
            return fallback_model
        except Exception as fallback_error:
            _get_log().error("Immediate fallback creation failed: %s", fallback_error)
        return None

    @staticmethod
    def _default_model_config(
        platform: ModelPlatformType, platform_hint: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if platform == ModelPlatformType.GEMINI and GeminiConfig:
            return GeminiConfig(temperature=0.2).as_dict()

        if platform == ModelPlatformType.OPENAI:
            return {"temperature": 0.2}

        return None

    @staticmethod
    def _resolve_base_url(
        platform: ModelPlatformType, platform_hint: Optional[str] = None
    ) -> Optional[str]:
        if platform.is_openai and _get_settings().openai_base_url:
            return _get_settings().openai_base_url
        return None

    @staticmethod
    def _parse_model_identifier(
        model_name: str, platform_hint: Optional[str] = None
    ) -> Tuple[str, str, Optional[str]]:
        raw_name = (model_name or "").strip()
        if not raw_name:
            return "", "", platform_hint

        hint = platform_hint
        api_model = base_model = raw_name
        lowered = raw_name.lower()

        if "/" in raw_name:
            provider, remainder = raw_name.split("/", 1)
            provider = provider.strip().lower()
            base_model = remainder.strip()
            api_model = base_model
            lowered = base_model.lower()

            if provider == "openai":
                hint = "openai"
            elif provider in {"google", "gemini"}:
                hint = "gemini"
            elif provider == "anthropic":
                hint = "anthropic"
        else:
            base_model = api_model = raw_name

        if hint is None:
            if lowered.startswith("gpt"):
                hint = "openai"
            elif lowered.startswith("gemini"):
                hint = "gemini"
            elif lowered.startswith("claude"):
                hint = "anthropic"

        if hint is None:
            hint = "openai"

        return api_model, base_model, hint

    @classmethod
    def _ensure_gemini_available(cls) -> bool:
        if cls._gemini_status_checked:
            return cls._gemini_key_valid

        cls._gemini_status_checked = True
        api_key = _get_settings().gemini_api_key
        if not api_key:
            cls._gemini_key_valid = False
            return False

        url = "https://generativelanguage.googleapis.com/v1beta/models"
        try:
            response = httpx.get(url, params={"key": api_key}, timeout=8.0)
            if response.status_code == 200 and response.json().get("models"):
                cls._gemini_key_valid = True
            else:
                _get_log().warning(
                    "Gemini models API returned %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                cls._gemini_key_valid = False
        except Exception as exc:
            _get_log().warning("Unable to validate Gemini API key: %s", exc)
            cls._gemini_key_valid = False

        return cls._gemini_key_valid
