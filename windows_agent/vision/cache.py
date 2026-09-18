"""In-memory vision cache to avoid redundant processing of captured observations."""

import logging
import time
from typing import Any, Dict, List, Optional

from windows_agent.vision.models import ScreenUnderstanding, TextRegion, UIElement

logger = logging.getLogger(__name__)


class VisionCache:
    """Caches OCR and UI detection results indexed by observation_id."""

    def __init__(self, max_items: int = 50, ttl_seconds: float = 300.0):
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        self._ocr_cache: Dict[str, Dict[str, Any]] = {}
        self._ui_cache: Dict[str, Dict[str, Any]] = {}
        self._understanding_cache: Dict[str, Dict[str, Any]] = {}

    def get_ocr(self, observation_id: str) -> Optional[List[TextRegion]]:
        """Retrieve cached OCR text regions for observation."""
        self.prune()
        entry = self._ocr_cache.get(observation_id)
        if entry and (time.time() - entry["stored_at"] <= self.ttl_seconds):
            logger.debug(f"VisionCache hit for OCR observation {observation_id}")
            return entry["data"]
        return None

    def set_ocr(self, observation_id: str, regions: List[TextRegion]) -> None:
        """Cache OCR text regions for observation."""
        self._ocr_cache[observation_id] = {
            "data": regions,
            "stored_at": time.time(),
        }
        self.prune()

    def get_ui_elements(self, observation_id: str) -> Optional[List[UIElement]]:
        """Retrieve cached UI elements for observation."""
        self.prune()
        entry = self._ui_cache.get(observation_id)
        if entry and (time.time() - entry["stored_at"] <= self.ttl_seconds):
            logger.debug(f"VisionCache hit for UI elements observation {observation_id}")
            return entry["data"]
        return None

    def set_ui_elements(self, observation_id: str, elements: List[UIElement]) -> None:
        """Cache detected UI elements for observation."""
        self._ui_cache[observation_id] = {
            "data": elements,
            "stored_at": time.time(),
        }
        self.prune()

    def get_understanding(self, observation_id: str) -> Optional[ScreenUnderstanding]:
        """Retrieve cached ScreenUnderstanding for observation."""
        self.prune()
        entry = self._understanding_cache.get(observation_id)
        if entry and (time.time() - entry["stored_at"] <= self.ttl_seconds):
            logger.debug(f"VisionCache hit for ScreenUnderstanding observation {observation_id}")
            return entry["data"]
        return None

    def set_understanding(self, observation_id: str, understanding: ScreenUnderstanding) -> None:
        """Cache ScreenUnderstanding for observation."""
        self._understanding_cache[observation_id] = {
            "data": understanding,
            "stored_at": time.time(),
        }
        self.prune()

    def prune(self) -> int:
        """Prune expired entries and excess count beyond max_items."""
        now = time.time()
        pruned_count = 0

        for cache_dict in (self._ocr_cache, self._ui_cache, self._understanding_cache):
            # 1. Expire by TTL
            expired_keys = [k for k, v in cache_dict.items() if now - v["stored_at"] > self.ttl_seconds]
            for k in expired_keys:
                del cache_dict[k]
                pruned_count += 1

            # 2. Prune excess items (oldest first)
            if len(cache_dict) > self.max_items:
                excess = len(cache_dict) - self.max_items
                sorted_keys = sorted(cache_dict.keys(), key=lambda k: cache_dict[k]["stored_at"])
                for k in sorted_keys[:excess]:
                    del cache_dict[k]
                    pruned_count += 1

        return pruned_count

    def clear(self) -> None:
        """Flush all cached vision entries."""
        self._ocr_cache.clear()
        self._ui_cache.clear()
        self._understanding_cache.clear()
