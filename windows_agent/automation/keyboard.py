"""Keyboard automation controller for Windows."""

import asyncio
import logging
import sys
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

# Common Windows Virtual Key mapping
VK_MAPPING = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "esc": 0x1B,
    "escape": 0x1B,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "win": 0x5B,
    "windows": 0x5B,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}


class KeyboardTypeParams(BaseModel):
    """Validation schema for keyboard.type parameters."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=5000, description="String to type")
    interval: float = Field(default=0.0, ge=0.0, le=2.0, description="Delay between keystrokes in seconds")


class KeyboardPressParams(BaseModel):
    """Validation schema for keyboard.press parameters."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1, max_length=30, description="Key name to press (e.g., 'enter', 'tab', 'a')")


class KeyboardHotkeyParams(BaseModel):
    """Validation schema for keyboard.hotkey parameters."""

    model_config = ConfigDict(extra="forbid")

    keys: List[str] = Field(..., min_length=2, max_length=5, description="Key combination (e.g., ['ctrl', 'c'])")

    @field_validator("keys")
    @classmethod
    def validate_keys(cls, v: List[str]) -> List[str]:
        cleaned = [k.strip().lower() for k in v]
        if any(len(k) == 0 for k in cleaned):
            raise ValueError("Keys must not be empty strings")
        return cleaned


class KeyboardController:
    """Controls keyboard typing, key presses, and modifier hotkeys on Windows."""

    def __init__(self, driver: Optional[Any] = None):
        self._driver = driver
        self.is_windows = sys.platform == "win32"

    async def type(self, params: KeyboardTypeParams) -> dict:
        """Type a sequence of characters."""
        if self._driver:
            return await self._driver.type(params.text, params.interval)

        if not self.is_windows:
            logger.info(f"[Non-Windows stub] keyboard.type length={len(params.text)}")
            return {"action": "type", "chars_typed": len(params.text), "platform": sys.platform}

        import ctypes
        user32 = ctypes.windll.user32
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_UNICODE = 0x0004

        for char in params.text:
            code = ord(char)
            # Unicode key events
            user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
            user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
            if params.interval > 0:
                await asyncio.sleep(params.interval)

        return {"action": "type", "chars_typed": len(params.text), "success": True}

    def _get_vk(self, key_name: str) -> int:
        """Resolve a key name or character to a virtual key code."""
        key_lower = key_name.lower()
        if key_lower in VK_MAPPING:
            return VK_MAPPING[key_lower]
        if len(key_name) == 1:
            return ord(key_name.upper())
        raise ValueError(f"Unsupported key name: '{key_name}'")

    async def press(self, params: KeyboardPressParams) -> dict:
        """Press and release a single key."""
        if self._driver:
            return await self._driver.press(params.key)

        vk = self._get_vk(params.key)

        if not self.is_windows:
            logger.info(f"[Non-Windows stub] keyboard.press '{params.key}' (vk=0x{vk:02X})")
            return {"action": "press", "key": params.key, "vk": vk, "platform": sys.platform}

        import ctypes
        user32 = ctypes.windll.user32
        KEYEVENTF_KEYUP = 0x0002

        user32.keybd_event(vk, 0, 0, 0)
        await asyncio.sleep(0.05)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

        return {"action": "press", "key": params.key, "vk": vk, "success": True}

    async def hotkey(self, params: KeyboardHotkeyParams) -> dict:
        """Press a combination of modifier and primary keys simultaneously."""
        if self._driver:
            return await self._driver.hotkey(params.keys)

        vks = [self._get_vk(k) for k in params.keys]

        if not self.is_windows:
            logger.info(f"[Non-Windows stub] keyboard.hotkey keys={params.keys}")
            return {"action": "hotkey", "keys": params.keys, "vks": vks, "platform": sys.platform}

        import ctypes
        user32 = ctypes.windll.user32
        KEYEVENTF_KEYUP = 0x0002

        # Press keys down in order
        for vk in vks:
            user32.keybd_event(vk, 0, 0, 0)
            await asyncio.sleep(0.02)

        # Release keys in reverse order
        for vk in reversed(vks):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            await asyncio.sleep(0.02)

        return {"action": "hotkey", "keys": params.keys, "vks": vks, "success": True}
