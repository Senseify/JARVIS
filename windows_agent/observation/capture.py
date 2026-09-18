"""Screen capture subsystem providing request-driven desktop observation."""

import asyncio
from datetime import datetime, timezone
import logging
import sys
from typing import Any, Dict, Optional
from uuid import uuid4

import mss
import mss.tools

from windows_agent.observation.models import CaptureScreenParams, ScreenState
from windows_agent.observation.store import ObservationStore

logger = logging.getLogger(__name__)


class ScreenCapture:
    """Performs request-driven screen captures and integrates with the ObservationStore."""

    def __init__(self, store: Optional[ObservationStore] = None):
        self.store = store or ObservationStore()
        self.is_windows = sys.platform == "win32"

    def get_active_window_info(self) -> Optional[Dict[str, Any]]:
        """Retrieve active/foreground window metadata if on Windows."""
        if not self.is_windows:
            return {"title": "Active Desktop", "handle": 1001, "platform": sys.platform}

        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            return {
                "handle": int(hwnd),
                "title": buff.value.strip(),
                "process_id": int(pid.value),
            }
        except Exception as e:
            logger.warning(f"Failed to query active window on Windows: {e}")
            return None

    async def capture(self, params: Optional[CaptureScreenParams] = None) -> ScreenState:
        """Capture the screen according to parameters and return structured ScreenState."""
        params = params or CaptureScreenParams()
        capture_id = str(uuid4())

        return await asyncio.to_thread(self._capture_sync, capture_id, params)

    def _capture_sync(self, capture_id: str, params: CaptureScreenParams) -> ScreenState:
        active_window = self.get_active_window_info()

        try:
            mss_cls = getattr(mss, "MSS", mss.mss)
            with mss_cls() as sct:
                monitors = sct.monitors
                mon_idx = params.monitor_index if params.monitor_index and params.monitor_index < len(monitors) else 1
                monitor_rect = monitors[mon_idx]

                if params.region:
                    capture_rect = {
                        "top": monitor_rect["top"] + params.region.top,
                        "left": monitor_rect["left"] + params.region.left,
                        "width": min(params.region.width, monitor_rect["width"]),
                        "height": min(params.region.height, monitor_rect["height"]),
                    }
                else:
                    capture_rect = monitor_rect

                sct_img = sct.grab(capture_rect)
                png_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)

                file_path = self.store.store(
                    capture_id=capture_id,
                    image_bytes=png_bytes,
                    metadata={
                        "monitor_index": mon_idx,
                        "rect": capture_rect,
                        "width": sct_img.width,
                        "height": sct_img.height,
                        "active_window": active_window,
                        "is_windows": self.is_windows,
                    },
                )

                return ScreenState(
                    capture_id=capture_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    width=sct_img.width,
                    height=sct_img.height,
                    monitor_index=mon_idx,
                    active_window=active_window,
                    file_path=file_path,
                    metadata={
                        "monitor_count": len(monitors) - 1,
                        "capture_rect": capture_rect,
                        "is_windows": self.is_windows,
                    },
                )

        except Exception as e:
            logger.warning(f"MSS screen capture fallback triggered: {e}")
            # Safe synthetic observation fallback for headless / display-less environments
            dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x00\x00\x00\x01\x00\x08\x02\x00\x00\x00"
            file_path = self.store.store(
                capture_id=capture_id,
                image_bytes=dummy_png,
                metadata={"synthetic": True, "error": str(e)},
            )
            return ScreenState(
                capture_id=capture_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                width=1920,
                height=1080,
                monitor_index=1,
                active_window=active_window,
                file_path=file_path,
                metadata={"synthetic": True, "reason": str(e)},
            )
