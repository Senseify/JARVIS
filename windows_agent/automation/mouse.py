"""Mouse automation controller for Windows."""

import asyncio
import logging
import sys
import time
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class MouseMoveParams(BaseModel):
    """Validation schema for mouse.move parameters."""

    model_config = ConfigDict(extra="forbid")

    x: int = Field(..., ge=0, description="Target X screen coordinate (pixels)")
    y: int = Field(..., ge=0, description="Target Y screen coordinate (pixels)")
    duration: float = Field(default=0.0, ge=0.0, le=10.0, description="Movement duration in seconds")


class MouseClickParams(BaseModel):
    """Validation schema for mouse.click parameters."""

    model_config = ConfigDict(extra="forbid")

    x: Optional[int] = Field(default=None, ge=0, description="Optional target X coordinate")
    y: Optional[int] = Field(default=None, ge=0, description="Optional target Y coordinate")
    button: Literal["left", "right", "middle"] = Field(default="left", description="Mouse button")
    clicks: int = Field(default=1, ge=1, le=10, description="Number of clicks")


class MouseDoubleClickParams(BaseModel):
    """Validation schema for mouse.double_click parameters."""

    model_config = ConfigDict(extra="forbid")

    x: Optional[int] = Field(default=None, ge=0, description="Optional target X coordinate")
    y: Optional[int] = Field(default=None, ge=0, description="Optional target Y coordinate")
    button: Literal["left", "right", "middle"] = Field(default="left", description="Mouse button")


class MouseController:
    """Controls mouse movement and clicks on Windows."""

    def __init__(self, driver: Optional[Any] = None):
        self._driver = driver
        self.is_windows = sys.platform == "win32"

    async def move(self, params: MouseMoveParams) -> dict:
        """Move cursor to target coordinates."""
        if self._driver:
            return await self._driver.move(params.x, params.y, params.duration)

        if not self.is_windows:
            logger.info(f"[Non-Windows stub] mouse.move to ({params.x}, {params.y})")
            return {"action": "move", "x": params.x, "y": params.y, "platform": sys.platform}

        # Native Windows implementation via user32
        import ctypes
        user32 = ctypes.windll.user32
        success = user32.SetCursorPos(params.x, params.y)
        if not success:
            raise OSError("Windows SetCursorPos failed to position cursor.")
        return {"action": "move", "x": params.x, "y": params.y, "success": True}

    async def click(self, params: MouseClickParams) -> dict:
        """Execute one or more clicks with the specified button."""
        if self._driver:
            return await self._driver.click(params.x, params.y, params.button, params.clicks)

        # If coordinates provided, move first
        if params.x is not None and params.y is not None:
            await self.move(MouseMoveParams(x=params.x, y=params.y))

        if not self.is_windows:
            logger.info(f"[Non-Windows stub] mouse.click {params.button} (x{params.clicks}) at ({params.x}, {params.y})")
            return {
                "action": "click",
                "button": params.button,
                "clicks": params.clicks,
                "x": params.x,
                "y": params.y,
                "platform": sys.platform,
            }

        import ctypes
        user32 = ctypes.windll.user32

        # Windows mouse event flags
        down_flags = {
            "left": 0x0002,   # MOUSEEVENTF_LEFTDOWN
            "right": 0x0008,  # MOUSEEVENTF_RIGHTDOWN
            "middle": 0x0020, # MOUSEEVENTF_MIDDLEDOWN
        }
        up_flags = {
            "left": 0x0004,   # MOUSEEVENTF_LEFTUP
            "right": 0x0010,  # MOUSEEVENTF_RIGHTUP
            "middle": 0x0040, # MOUSEEVENTF_MIDDLEUP
        }

        down_flag = down_flags[params.button]
        up_flag = up_flags[params.button]

        for _ in range(params.clicks):
            user32.mouse_event(down_flag, 0, 0, 0, 0)
            await asyncio.sleep(0.05)
            user32.mouse_event(up_flag, 0, 0, 0, 0)
            if params.clicks > 1:
                await asyncio.sleep(0.05)

        return {
            "action": "click",
            "button": params.button,
            "clicks": params.clicks,
            "x": params.x,
            "y": params.y,
            "success": True,
        }

    async def double_click(self, params: MouseDoubleClickParams) -> dict:
        """Execute a double click."""
        return await self.click(
            MouseClickParams(
                x=params.x,
                y=params.y,
                button=params.button,
                clicks=2,
            )
        )
