"""Unified vision service coordinating screen capture, OCR, UI detection, and screen understanding."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

from windows_agent.observation.capture import ScreenCapture
from windows_agent.observation.models import ScreenState
from windows_agent.observation.store import ObservationStore
from windows_agent.vision.cache import VisionCache
from windows_agent.vision.models import (
    ScreenUnderstanding,
    TextRegion,
    UIElement,
)
from windows_agent.vision.ocr import OCREngine
from windows_agent.vision.ui_detector import UIDetector

logger = logging.getLogger(__name__)


class VisionService:
    """Service orchestrating visual awareness, OCR, UI element discovery, and unified screen understanding."""

    def __init__(
        self,
        capture: ScreenCapture,
        store: ObservationStore,
        cache: Optional[VisionCache] = None,
        ocr_engine: Optional[OCREngine] = None,
        ui_detector: Optional[UIDetector] = None,
    ):
        self.capture = capture
        self.store = store
        self.cache = cache or VisionCache()
        self.ocr = ocr_engine or OCREngine(store=self.store, cache=self.cache)
        self.ui_detector = ui_detector or UIDetector(cache=self.cache)

    async def get_or_capture_observation(self, observation_id: Optional[str] = None) -> ScreenState:
        """Fetch existing ScreenState by observation ID or trigger a new request-driven capture."""
        if observation_id:
            record = self.store.get(observation_id)
            if not record:
                raise ValueError(f"Observation ID '{observation_id}' not found in observation store.")

            meta = record.get("metadata", {})
            return ScreenState(
                capture_id=observation_id,
                timestamp=record.get("timestamp", datetime.now(timezone.utc).isoformat()),
                width=meta.get("width", 1920),
                height=meta.get("height", 1080),
                monitor_index=meta.get("monitor_index", 1),
                active_window=meta.get("active_window"),
                file_path=record.get("file_path"),
                metadata=meta,
            )

        return await self.capture.capture()

    async def perform_ocr(self, observation_id: Optional[str] = None) -> Tuple[str, List[TextRegion]]:
        """Perform request-driven OCR on target observation, returning observation ID and text regions."""
        state = await self.get_or_capture_observation(observation_id)
        cid = state.capture_id
        regions = await self.ocr.extract_text(cid)
        return cid, regions

    async def detect_ui(
        self,
        observation_id: Optional[str] = None,
        window_handle: Optional[int] = None,
    ) -> Tuple[str, List[UIElement]]:
        """Detect native UI controls on target observation, returning observation ID and UI elements."""
        state = await self.get_or_capture_observation(observation_id)
        cid = state.capture_id
        elements = await self.ui_detector.detect_elements(cid, window_handle=window_handle)
        return cid, elements

    async def understand_screen(self, observation_id: Optional[str] = None) -> ScreenUnderstanding:
        """Generate unified structured ScreenUnderstanding combining observation, OCR, and UI elements."""
        state = await self.get_or_capture_observation(observation_id)
        cid = state.capture_id

        # Check cache
        cached = self.cache.get_understanding(cid)
        if cached:
            return cached

        # Execute OCR and UI element detection
        active_handle = state.active_window.get("handle") if state.active_window else None
        text_regions_task = self.ocr.extract_text(cid)
        ui_elements_task = self.ui_detector.detect_elements(cid, window_handle=active_handle)

        text_regions, ui_elements = await asyncio.gather(text_regions_task, ui_elements_task)

        understanding = ScreenUnderstanding(
            observation_id=cid,
            timestamp=datetime.now(timezone.utc).isoformat(),
            screen_state=state,
            active_window=state.active_window,
            text_regions=text_regions,
            ui_elements=ui_elements,
        )

        self.cache.set_understanding(cid, understanding)
        return understanding
