"""
NewsAPI-powered toolkit for CAMEL agents.

Wraps the official `newsapi-python` client and exposes news fetching functions as
FunctionTools so that CAMEL workforces can fetch recent crypto/business news.
Requires `pip install newsapi-python`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from core.logging import log
from core.config import settings

try:  # pragma: no cover - optional dependency
    from camel.toolkits import FunctionTool
    CAMEL_TOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover
    FunctionTool = None  # type: ignore
    CAMEL_TOOLS_AVAILABLE = False

try:  # pragma: no cover - optional dependency
    from newsapi import NewsApiClient
    NEWSAPI_AVAILABLE = True
except (ImportError, ModuleNotFoundError):  # pragma: no cover
    NewsApiClient = None  # type: ignore
    NEWSAPI_AVAILABLE = False


class NewsAPIToolkit:
    """Expose NewsAPI search helpers to CAMEL agents."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._client: Optional["NewsApiClient"] = None  # String annotation for forward reference
        self._api_key = api_key or getattr(settings, 'news_api_key', None)
        self._business_sources: Optional[List[str]] = None  # Cached business sources

    async def initialize(self) -> None:
        if not NEWSAPI_AVAILABLE:
            raise ImportError("newsapi-python package is not installed. Install with `pip install newsapi-python`.")
        if not CAMEL_TOOLS_AVAILABLE:
            raise ImportError("CAMEL function tools are required for NewsAPI toolkit.")

        if not self._api_key:
            raise ValueError("NEWS_API environment variable is not set. Please provide a NewsAPI key.")

        if not self._client:
            self._client = NewsApiClient(api_key=self._api_key)
            log.info("NewsAPI client initialised.")
            
            # Pre-fetch and cache business sources
            try:
                await self._cache_business_sources()
            except Exception as e:
                log.warning(f"Failed to cache business sources on initialization: {e}")

    async def _ensure_client(self) -> "NewsApiClient":
        await self.initialize()
        if not self._client:
            raise RuntimeError("NewsAPI client failed to initialise.")
        return self._client

    async def _cache_business_sources(self) -> None:
        """Fetch and cache business/finance news sources."""
        if self._business_sources is not None:
            return  # Already cached
            
        try:
            client = await self._ensure_client()
            sources_response = client.get_sources(
                category='business',
                language='en',
                country='us'
            )
            
            if sources_response and sources_response.get('status') == 'ok':
                sources = sources_response.get('sources', [])
                self._business_sources = [s.get('id', '') for s in sources if s.get('id')]
                log.info(f"Cached {len(self._business_sources)} business news sources")
            else:
                log.warning(f"Failed to fetch business sources: {sources_response}")
                self._business_sources = []
        except Exception as e:
            log.warning(f"Error caching business sources: {e}")
            self._business_sources = []

    async def get_top_headlines(
        self,
        q: Optional[str] = None,
        sources: Optional[str] = None,
        category: str = 'business',
        language: str = 'en',
        country: str = 'us',
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Fetch top headlines from NewsAPI.
        
        Args:
            q: Keywords or phrases to search for (e.g., 'bitcoin', 'crypto')
            sources: Comma-separated string of source identifiers (e.g., 'bbc-news,the-verge')
            category: News category (default: 'business')
            language: Language code (default: 'en')
            country: Country code (default: 'us')
            page_size: Number of results (default: 20, max: 100)
        """
        client = await self._ensure_client()
        
        # If no sources provided and we have cached business sources, use them
        if not sources and self._business_sources:
            sources = ','.join(self._business_sources[:10])  # Limit to top 10 sources
        
        try:
            response = client.get_top_headlines(
                q=q,
                sources=sources,
                category=category if not sources else None,  # category and sources are mutually exclusive
                language=language,
                country=country if not sources else None,  # country and sources are mutually exclusive
                page_size=min(page_size, 100)
            )
            
            if response and response.get('status') == 'ok':
                articles = response.get('articles', [])
                return {
                    "success": True,
                    "query": q or "top headlines",
                    "total_results": response.get('totalResults', len(articles)),
                    "articles": articles[:page_size],
                }
            else:
                return {
                    "success": False,
                    "error": response.get('message', 'Unknown error'),
                    "articles": [],
                }
        except Exception as e:
            log.error(f"Error fetching top headlines: {e}")
            return {
                "success": False,
                "error": str(e),
                "articles": [],
            }

    async def get_everything(
        self,
        q: Optional[str] = None,
        sources: Optional[str] = None,
        domains: Optional[str] = None,
        from_param: Optional[str] = None,
        to: Optional[str] = None,
        language: str = 'en',
        sort_by: str = 'relevancy',
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Search all articles from NewsAPI.
        
        Args:
            q: Keywords or phrases to search for (e.g., 'bitcoin')
            sources: Comma-separated string of source identifiers
            domains: Comma-separated string of domains to restrict search (e.g., 'bbc.co.uk,techcrunch.com')
            from_param: Start date in YYYY-MM-DD format (default: 7 days ago)
            to: End date in YYYY-MM-DD format (default: today)
            language: Language code (default: 'en')
            sort_by: Sort order: 'relevancy', 'popularity', or 'publishedAt' (default: 'relevancy')
            page: Page number (default: 1)
            page_size: Number of results per page (default: 20, max: 100)
        """
        client = await self._ensure_client()
        
        # Default to last 7 days if no dates provided
        if not from_param:
            from_date = datetime.now() - timedelta(days=7)
            from_param = from_date.strftime('%Y-%m-%d')
        if not to:
            to = datetime.now().strftime('%Y-%m-%d')
        
        # If no sources provided and we have cached business sources, use them
        if not sources and self._business_sources:
            sources = ','.join(self._business_sources[:10])
        
        try:
            response = client.get_everything(
                q=q,
                sources=sources,
                domains=domains,
                from_param=from_param,
                to=to,
                language=language,
                sort_by=sort_by,
                page=page,
                page_size=min(page_size, 100)
            )
            
            if response and response.get('status') == 'ok':
                articles = response.get('articles', [])
                return {
                    "success": True,
                    "query": q or "all articles",
                    "total_results": response.get('totalResults', len(articles)),
                    "page": page,
                    "articles": articles,
                }
            else:
                return {
                    "success": False,
                    "error": response.get('message', 'Unknown error'),
                    "articles": [],
                }
        except Exception as e:
            log.error(f"Error fetching articles: {e}")
            return {
                "success": False,
                "error": str(e),
                "articles": [],
            }

    async def get_sources(
        self,
        category: Optional[str] = 'business',
        language: str = 'en',
        country: str = 'us',
    ) -> Dict[str, Any]:
        """
        Get available news sources from NewsAPI.
        
        Args:
            category: News category filter (default: 'business')
            language: Language code (default: 'en')
            country: Country code (default: 'us')
        """
        client = await self._ensure_client()
        
        try:
            response = client.get_sources(
                category=category,
                language=language,
                country=country
            )
            
            if response and response.get('status') == 'ok':
                sources = response.get('sources', [])
                # Update cache if fetching business sources
                if category == 'business':
                    self._business_sources = [s.get('id', '') for s in sources if s.get('id')]
                
                return {
                    "success": True,
                    "category": category,
                    "sources": sources,
                }
            else:
                return {
                    "success": False,
                    "error": response.get('message', 'Unknown error'),
                    "sources": [],
                }
        except Exception as e:
            log.error(f"Error fetching sources: {e}")
            return {
                "success": False,
                "error": str(e),
                "sources": [],
            }

    def get_top_headlines_tool(self):
        """Get tool for fetching top headlines."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit = self

        async def newsapi_top_headlines(
            q: Optional[str] = None,
            sources: Optional[str] = None,
            category: str = 'business',
            language: str = 'en',
            country: str = 'us',
            page_size: int = 20,
        ) -> Dict[str, Any]:
            """
            Fetch top headlines from NewsAPI. Useful for getting the latest crypto/business news.

            Args:
                q: Keywords or phrases to search for (e.g., 'bitcoin', 'crypto', 'ethereum')
                sources: Comma-separated string of source identifiers (e.g., 'bbc-news,the-verge')
                category: News category - 'business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology' (default: 'business')
                language: Language code (default: 'en')
                country: Country code (default: 'us')
                page_size: Number of results to return (default: 20, max: 100)
            """
            return await toolkit.get_top_headlines(
                q=q,
                sources=sources,
                category=category,
                language=language,
                country=country,
                page_size=max(1, min(page_size, 100)),
            )

        newsapi_top_headlines.__name__ = "newsapi_top_headlines"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(newsapi_top_headlines)

        # ✅ CRITICAL: Completely override schema to ensure OpenAI compliance
        # Don't rely on auto-generation - manually create schema from scratch to avoid issues
        # OpenAI function schemas don't support 'default' or 'nullable' in properties.
        # Optional parameters are those NOT in the 'required' array.
        # IMPORTANT: All parameters have defaults (q=None, category='business', etc.), so none are required
        schema = {
            "type": "function",
            "function": {
                "name": "newsapi_top_headlines",
                "description": (
                    "Fetch top headlines from NewsAPI. Useful for getting the latest crypto/business news.\n\n"
                    "Args:\n"
                    "  q: Optional keywords or phrases to search for (e.g., 'bitcoin', 'crypto', 'ethereum'). Default: None\n"
                    "  sources: Optional comma-separated string of source identifiers (e.g., 'bbc-news,the-verge'). Default: None\n"
                    "  category: News category - 'business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology'. Default: 'business'\n"
                    "  language: Language code. Default: 'en'\n"
                    "  country: Country code. Default: 'us'\n"
                    "  page_size: Number of results to return (1-100). Default: 20"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "q": {
                            "type": "string",
                            "description": "Optional keywords or phrases to search for (e.g., 'bitcoin', 'crypto', 'ethereum'). Default: None"
                        },
                        "sources": {
                            "type": "string",
                            "description": "Optional comma-separated string of source identifiers (e.g., 'bbc-news,the-verge'). Default: None"
                        },
                        "category": {
                            "type": "string",
                            "description": "News category - 'business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology'. Default: 'business'",
                        },
                        "language": {
                            "type": "string",
                            "description": "Language code. Default: 'en'"
                        },
                        "country": {
                            "type": "string",
                            "description": "Country code. Default: 'us'"
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of results to return (1-100). Default: 20",
                        },
                    },
                    "required": [],  # All parameters are optional (have defaults in function) - empty array means no required params
                },
            },
        }

        # ✅ Force schema override BEFORE tool is used anywhere - completely replace auto-generated schema
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema

        return tool

    def get_everything_tool(self):
        """Get tool for searching all articles."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit = self

        async def newsapi_everything(
            q: Optional[str] = None,
            sources: Optional[str] = None,
            domains: Optional[str] = None,
            from_param: Optional[str] = None,
            to: Optional[str] = None,
            language: str = 'en',
            sort_by: str = 'relevancy',
            page: int = 1,
            page_size: int = 20,
        ) -> Dict[str, Any]:
            """
            Search all articles from NewsAPI. Useful for finding historical news or specific topics.

            Args:
                q: Keywords or phrases to search for (e.g., 'bitcoin', 'crypto')
                sources: Comma-separated string of source identifiers
                domains: Comma-separated string of domains to restrict search (e.g., 'bbc.co.uk,techcrunch.com')
                from_param: Start date in YYYY-MM-DD format (default: 7 days ago)
                to: End date in YYYY-MM-DD format (default: today)
                language: Language code (default: 'en')
                sort_by: Sort order - 'relevancy', 'popularity', or 'publishedAt' (default: 'relevancy')
                page: Page number (default: 1)
                page_size: Number of results per page (default: 20, max: 100)
            """
            return await toolkit.get_everything(
                q=q,
                sources=sources,
                domains=domains,
                from_param=from_param,
                to=to,
                language=language,
                sort_by=sort_by,
                page=page,
                page_size=max(1, min(page_size, 100)),
            )

        newsapi_everything.__name__ = "newsapi_everything"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(newsapi_everything)

        # ✅ CRITICAL: Completely override schema to ensure OpenAI compliance
        # Don't rely on auto-generation - manually create schema from scratch to avoid issues
        # OpenAI function schemas don't support 'default' or 'nullable' in properties.
        # Optional parameters are those NOT in the 'required' array.
        # IMPORTANT: All parameters have defaults (q=None, language='en', etc.), so none are required
        schema = {
            "type": "function",
            "function": {
                "name": "newsapi_everything",
                "description": (
                    "Search all articles from NewsAPI. Useful for finding historical news or specific topics.\n\n"
                    "Args:\n"
                    "  q: Optional keywords or phrases to search for (e.g., 'bitcoin', 'crypto'). Default: None\n"
                    "  sources: Optional comma-separated string of source identifiers. Default: None\n"
                    "  domains: Optional comma-separated string of domains to restrict search (e.g., 'bbc.co.uk,techcrunch.com'). Default: None\n"
                    "  from_param: Optional start date in YYYY-MM-DD format. Default: 7 days ago\n"
                    "  to: Optional end date in YYYY-MM-DD format. Default: today\n"
                    "  language: Language code. Default: 'en'\n"
                    "  sort_by: Sort order - 'relevancy', 'popularity', or 'publishedAt'. Default: 'relevancy'\n"
                    "  page: Page number. Default: 1\n"
                    "  page_size: Number of results per page (1-100). Default: 20"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "q": {
                            "type": "string",
                            "description": "Optional keywords or phrases to search for (e.g., 'bitcoin', 'crypto'). Default: None"
                        },
                        "sources": {
                            "type": "string",
                            "description": "Optional comma-separated string of source identifiers. Default: None"
                        },
                        "domains": {
                            "type": "string",
                            "description": "Optional comma-separated string of domains to restrict search (e.g., 'bbc.co.uk,techcrunch.com'). Default: None"
                        },
                        "from_param": {
                            "type": "string",
                            "description": "Optional start date in YYYY-MM-DD format. Default: 7 days ago"
                        },
                        "to": {
                            "type": "string",
                            "description": "Optional end date in YYYY-MM-DD format. Default: today"
                        },
                        "language": {
                            "type": "string",
                            "description": "Language code. Default: 'en'"
                        },
                        "sort_by": {
                            "type": "string",
                            "description": "Sort order - 'relevancy', 'popularity', or 'publishedAt'. Default: 'relevancy'",
                            "enum": ["relevancy", "popularity", "publishedAt"]
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number. Default: 1",
                            "minimum": 1
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of results per page (1-100). Default: 20",
                            "minimum": 1,
                            "maximum": 100
                        },
                    },
                    "required": [],  # All parameters are optional (have defaults in function) - empty array means no required params
                },
            },
        }

        # ✅ Force schema override BEFORE tool is used anywhere - completely replace auto-generated schema
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema

        return tool

    def get_sources_tool(self):
        """Get tool for fetching available sources."""
        if not CAMEL_TOOLS_AVAILABLE or FunctionTool is None:
            raise ImportError("CAMEL function tools are not installed.")

        toolkit = self

        async def newsapi_sources(
            category: Optional[str] = 'business',
            language: str = 'en',
            country: str = 'us',
        ) -> Dict[str, Any]:
            """
            Get available news sources from NewsAPI. Useful for finding relevant business/finance sources.

            Args:
                category: News category filter - 'business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology', or None for all (default: 'business')
                language: Language code (default: 'en')
                country: Country code (default: 'us')
            """
            return await toolkit.get_sources(
                category=category,
                language=language,
                country=country
            )

        newsapi_sources.__name__ = "newsapi_sources"
        # ✅ PURE CAMEL: Use shared async wrapper for proper event loop handling
        from core.camel_tools.async_wrapper import create_function_tool
        tool = create_function_tool(newsapi_sources)

        # ✅ CRITICAL: Completely override schema to ensure OpenAI compliance
        # Don't rely on auto-generation - manually create schema from scratch to avoid issues
        # OpenAI function schemas don't support 'default' or 'nullable' in properties.
        # Optional parameters are those NOT in the 'required' array.
        # IMPORTANT: All parameters have defaults (category='business', language='en', country='us'), so none are required
        schema = {
            "type": "function",
            "function": {
                "name": "newsapi_sources",
                "description": (
                    "Get available news sources from NewsAPI. Useful for finding relevant business/finance sources.\n\n"
                    "Args:\n"
                    "  category: Optional news category filter - 'business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology', or None for all. Default: 'business'\n"
                    "  language: Language code. Default: 'en'\n"
                    "  country: Country code. Default: 'us'"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Optional news category filter - 'business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology', or None for all. Default: 'business'",
                            "enum": ["business", "entertainment", "general", "health", "science", "sports", "technology"]
                        },
                        "language": {
                            "type": "string",
                            "description": "Language code. Default: 'en'"
                        },
                        "country": {
                            "type": "string",
                            "description": "Country code. Default: 'us'"
                        },
                    },
                    "required": [],  # All parameters are optional (have defaults in function) - empty array means no required params
                },
            },
        }

        # ✅ Force schema override BEFORE tool is used anywhere - completely replace auto-generated schema
        tool.openai_tool_schema = schema
        # Also ensure the tool's internal schema cache is updated
        if hasattr(tool, '_openai_tool_schema'):
            tool._openai_tool_schema = schema
        if hasattr(tool, '_schema'):
            tool._schema = schema

        return tool

    def get_all_tools(self):
        """Get all tools in this toolkit."""
        return [
            self.get_top_headlines_tool(),
            self.get_everything_tool(),
            self.get_sources_tool(),
        ]


__all__ = ["NewsAPIToolkit"]

