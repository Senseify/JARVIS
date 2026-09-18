"""Native Windows UI element detection using desktop control and accessibility APIs."""

import asyncio
import logging
import sys
from typing import Callable, Dict, List, Optional

from windows_agent.vision.cache import VisionCache
from windows_agent.vision.models import BoundingBox, Point, UIElement

logger = logging.getLogger(__name__)


class UIDetector:
    """Detects native desktop UI controls and extracts their structural attributes and coordinates."""

    def __init__(
        self,
        cache: Optional[VisionCache] = None,
        custom_provider: Optional[Callable[[Optional[int]], List[UIElement]]] = None,
    ):
        self.cache = cache or VisionCache()
        self.custom_provider = custom_provider
        self.is_windows = sys.platform == "win32"

    async def detect_elements(
        self,
        observation_id: Optional[str] = None,
        window_handle: Optional[int] = None,
    ) -> List[UIElement]:
        """Detect UI elements in the target window or active desktop."""
        # Check cache if observation_id is specified
        if observation_id:
            cached = self.cache.get_ui_elements(observation_id)
            if cached is not None:
                if window_handle is not None:
                    return [el for el in cached if el.element_id == str(window_handle)]
                return cached

        # Custom provider hook (for tests)
        if self.custom_provider is not None:
            elements = await asyncio.to_thread(self.custom_provider, window_handle)
            if observation_id:
                self.cache.set_ui_elements(observation_id, elements)
            return elements

        # Native Windows control detection
        if self.is_windows:
            elements = await asyncio.to_thread(self._detect_windows_elements, window_handle)
            if observation_id:
                self.cache.set_ui_elements(observation_id, elements)
            return elements

        # Clean non-Windows fallback
        logger.debug(f"UI element detection requested on non-Windows platform '{sys.platform}'. Returning empty.")
        empty_list: List[UIElement] = []
        if observation_id:
            self.cache.set_ui_elements(observation_id, empty_list)
        return empty_list

    def _detect_windows_elements(self, target_hwnd: Optional[int] = None) -> List[UIElement]:
        """Enumerate controls using native Win32 User32 APIs via ctypes."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # If no specific handle requested, target current foreground window
        parent_hwnd = target_hwnd or user32.GetForegroundWindow()
        if not parent_hwnd:
            return []

        elements: List[UIElement] = []
        focused_hwnd = user32.GetFocus()

        def _classify_control(class_name: str, style: int) -> tuple[str, List[str]]:
            cname = class_name.lower()
            # Checkbox styles (BS_CHECKBOX = 0x2, BS_AUTOCHECKBOX = 0x3, BS_3STATE = 0x5)
            if cname == "button":
                btn_type = style & 0xF
                if btn_type in (0x2, 0x3, 0x5, 0x6):
                    return "checkbox", ["click", "toggle"]
                if btn_type in (0x4, 0x9):
                    return "radio_button", ["click", "select"]
                return "button", ["click"]
            if cname in ("edit", "richedit", "richedit20w", "richedit50w"):
                return "text_field", ["type", "click", "clear", "focus"]
            if cname in ("static",):
                return "static_text", []
            if cname in ("combobox",):
                return "combo_box", ["click", "select"]
            if cname in ("listbox",):
                return "list_box", ["click", "select"]
            if cname in ("syslink", "hyperlink"):
                return "link", ["click"]
            if cname in ("#32768", "menu"):
                return "menu", ["click", "select"]
            return "control", ["click"]

        # Callback for EnumChildWindows
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def enum_child_proc(hwnd, lparam):
            try:
                # Class name
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buf, 256)
                class_name = class_buf.value.strip()

                # Text / Title
                length = user32.GetWindowTextLengthW(hwnd)
                text_buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, text_buf, length + 1)
                text = text_buf.value.strip()

                # Bounding Rect
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top

                if w <= 0 or h <= 0:
                    return True

                bbox = BoundingBox(
                    left=rect.left,
                    top=rect.top,
                    width=w,
                    height=h,
                )

                # Window style
                style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE = -16

                element_type, capabilities = _classify_control(class_name, style)
                is_visible = bool(user32.IsWindowVisible(hwnd))
                is_enabled = bool(user32.IsWindowEnabled(hwnd))
                is_focused = bool(focused_hwnd == hwnd)

                elements.append(
                    UIElement(
                        element_id=str(hwnd),
                        element_type=element_type,
                        name=text or class_name,
                        bounding_box=bbox,
                        is_enabled=is_enabled,
                        is_visible=is_visible,
                        is_focused=is_focused,
                        interaction_capabilities=capabilities,
                    )
                )
            except Exception as e:
                logger.debug(f"Error inspecting child control {hwnd}: {e}")

            return True

        # Enumerate children of parent window
        cb = WNDENUMPROC(enum_child_proc)
        user32.EnumChildWindows(parent_hwnd, cb, 0)

        return elements
