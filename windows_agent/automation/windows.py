"""Window management and discovery controller for Windows."""

import asyncio
import logging
import sys
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


class WindowListParams(BaseModel):
    """Validation schema for window.list parameters."""

    model_config = ConfigDict(extra="forbid")

    include_invisible: bool = Field(default=False, description="Whether to include hidden/invisible windows")


class WindowFocusParams(BaseModel):
    """Validation schema for window.focus parameters."""

    model_config = ConfigDict(extra="forbid")

    handle: Optional[int] = Field(default=None, description="Window handle (HWND)")
    title: Optional[str] = Field(default=None, min_length=1, description="Window title or substring")

    @model_validator(mode="after")
    def check_handle_or_title(self) -> "WindowFocusParams":
        if self.handle is None and (self.title is None or len(self.title.strip()) == 0):
            raise ValueError("Either 'handle' or 'title' must be provided to focus a window.")
        return self


class WindowController:
    """Controls window enumeration and focus on Windows."""

    def __init__(self, driver: Optional[Any] = None):
        self._driver = driver
        self.is_windows = sys.platform == "win32"

    async def list_windows(self, params: WindowListParams) -> dict:
        """Enumerate running top-level windows."""
        if self._driver:
            return await self._driver.list_windows(params.include_invisible)

        if not self.is_windows:
            logger.info("[Non-Windows stub] window.list called")
            return {
                "windows": [
                    {"handle": 1001, "title": "Mock Desktop Window", "is_visible": True, "process_id": 1234},
                    {"handle": 1002, "title": "Mock Application", "is_visible": True, "process_id": 5678},
                ],
                "platform": sys.platform,
                "total_count": 2,
            }

        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        windows_found = []

        # Windows callback signature: BOOL CALLBACK EnumWindowsProc(HWND hwnd, LPARAM lParam)
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def enum_callback(hwnd, lparam):
            is_visible = bool(user32.IsWindowVisible(hwnd))
            if not is_visible and not params.include_invisible:
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0 and not params.include_invisible:
                return True

            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()

            if not title and not params.include_invisible:
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            windows_found.append({
                "handle": int(hwnd),
                "title": title,
                "is_visible": is_visible,
                "process_id": int(pid.value),
            })
            return True

        cb = WNDENUMPROC(enum_callback)
        user32.EnumWindows(cb, 0)

        return {
            "windows": windows_found,
            "total_count": len(windows_found),
        }

    async def focus(self, params: WindowFocusParams) -> dict:
        """Bring target window to foreground."""
        if self._driver:
            return await self._driver.focus(params.handle, params.title)

        if not self.is_windows:
            logger.info(f"[Non-Windows stub] window.focus handle={params.handle} title='{params.title}'")
            return {
                "focused": True,
                "handle": params.handle or 1001,
                "title": params.title or "Mock Window",
                "platform": sys.platform,
            }

        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        target_hwnd = params.handle

        if target_hwnd is None and params.title:
            # Search by title substring
            search_title = params.title.lower()
            matching_hwnds = []

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            def find_callback(hwnd, lparam):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        if search_title in buff.value.lower():
                            matching_hwnds.append(int(hwnd))
                return True

            cb = WNDENUMPROC(find_callback)
            user32.EnumWindows(cb, 0)

            if not matching_hwnds:
                raise ValueError(f"No visible window found matching title: '{params.title}'")
            target_hwnd = matching_hwnds[0]

        SW_RESTORE = 9
        user32.ShowWindow(target_hwnd, SW_RESTORE)
        success = bool(user32.SetForegroundWindow(target_hwnd))

        return {
            "focused": success,
            "handle": target_hwnd,
            "title": params.title,
        }
