"""Automation package for Windows Agent computer control."""

from windows_agent.automation.applications import (
    ApplicationController,
    AppLaunchParams,
    DEFAULT_APPLICATION_ALLOWLIST,
)
from windows_agent.automation.keyboard import (
    KeyboardController,
    KeyboardHotkeyParams,
    KeyboardPressParams,
    KeyboardTypeParams,
)
from windows_agent.automation.mouse import (
    MouseClickParams,
    MouseController,
    MouseDoubleClickParams,
    MouseMoveParams,
)
from windows_agent.automation.receipt import ActionReceipt, ReceiptTracker
from windows_agent.automation.windows import (
    WindowController,
    WindowFocusParams,
    WindowListParams,
)

__all__ = [
    "ActionReceipt",
    "ReceiptTracker",
    "MouseController",
    "MouseMoveParams",
    "MouseClickParams",
    "MouseDoubleClickParams",
    "KeyboardController",
    "KeyboardTypeParams",
    "KeyboardPressParams",
    "KeyboardHotkeyParams",
    "WindowController",
    "WindowListParams",
    "WindowFocusParams",
    "ApplicationController",
    "AppLaunchParams",
    "DEFAULT_APPLICATION_ALLOWLIST",
]
