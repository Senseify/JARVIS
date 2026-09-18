"""Knowledge retrieval service partitioning local facts, memory, and optional web retrieval."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Provides local knowledge facts and transparent retrieval interfaces.

    Strictly demarcates:
    - LOCAL KNOWLEDGE (static verified facts and documentation)
    - MEMORY (user facts, preferences, past task outcomes)
    - SCREEN INFORMATION (live OCR and window state)
    - LIVE WEB INFORMATION (optional external search)
    """

    def __init__(self, web_search_enabled: bool = False) -> None:
        self.web_search_enabled = web_search_enabled
        self._local_facts: dict[str, str] = {
            "jarvis_os": "JARVIS is an autonomous, local-first personal AI agent with verified execution.",
            "supported_platforms": "Windows desktop agent with modular architecture for macOS and Linux.",
            "capabilities": "Mouse, keyboard, window control, screen capture, OCR, UI tree inspection, persistent memory.",
        }

    def get_local_fact(self, topic: str) -> str | None:
        """Retrieve verified local knowledge fact."""
        return self._local_facts.get(topic.lower().strip())

    def search_local(self, query: str) -> list[dict[str, str]]:
        """Search local verified documentation and facts."""
        q = query.lower()
        results = []
        for key, val in self._local_facts.items():
            if q in key or q in val.lower():
                results.append({"topic": key, "content": val, "source": "local_knowledge"})
        return results

    async def search_web(self, query: str) -> dict[str, Any]:
        """Query optional live web search provider."""
        if not self.web_search_enabled:
            return {
                "source": "web",
                "available": False,
                "results": [],
                "message": "Live web search provider is not configured or disabled in offline mode.",
            }
        # Web search provider placeholder
        return {
            "source": "web",
            "available": True,
            "results": [],
            "message": "No external search provider configured.",
        }
