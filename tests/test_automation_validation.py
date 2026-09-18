"""Unit tests for Phase 4 desktop automation parameter validation and allowlists."""

import pytest
from pydantic import ValidationError

from windows_agent.automation.applications import (
    ApplicationController,
    AppLaunchParams,
    DEFAULT_APPLICATION_ALLOWLIST,
)
from windows_agent.automation.keyboard import (
    KeyboardHotkeyParams,
    KeyboardPressParams,
    KeyboardTypeParams,
)
from windows_agent.automation.mouse import (
    MouseClickParams,
    MouseDoubleClickParams,
    MouseMoveParams,
)
from windows_agent.automation.receipt import ActionReceipt, ReceiptTracker
from windows_agent.automation.windows import (
    WindowFocusParams,
    WindowListParams,
)


# -------------------------------------------------------------
# 1. Mouse Validation Tests
# -------------------------------------------------------------
def test_mouse_move_validation():
    """Verify MouseMoveParams validates coordinates and rejects negatives."""
    valid = MouseMoveParams(x=100, y=200, duration=0.5)
    assert valid.x == 100
    assert valid.y == 200
    assert valid.duration == 0.5

    # Negative coordinates must be rejected
    with pytest.raises(ValidationError):
        MouseMoveParams(x=-1, y=100)
    with pytest.raises(ValidationError):
        MouseMoveParams(x=100, y=-5)
    # Negative or excessive duration must be rejected
    with pytest.raises(ValidationError):
        MouseMoveParams(x=100, y=100, duration=-1.0)
    with pytest.raises(ValidationError):
        MouseMoveParams(x=100, y=100, duration=15.0)


def test_mouse_click_validation():
    """Verify MouseClickParams validates button and click count."""
    valid = MouseClickParams(x=50, y=50, button="right", clicks=2)
    assert valid.button == "right"
    assert valid.clicks == 2

    # Invalid button name
    with pytest.raises(ValidationError):
        MouseClickParams(button="invalid_button")

    # Zero or negative clicks
    with pytest.raises(ValidationError):
        MouseClickParams(clicks=0)
    with pytest.raises(ValidationError):
        MouseClickParams(clicks=-2)


def test_mouse_double_click_validation():
    """Verify MouseDoubleClickParams accepts valid buttons."""
    valid = MouseDoubleClickParams(x=10, y=20, button="left")
    assert valid.x == 10
    assert valid.button == "left"

    with pytest.raises(ValidationError):
        MouseDoubleClickParams(button="unsupported")


# -------------------------------------------------------------
# 2. Keyboard Validation Tests
# -------------------------------------------------------------
def test_keyboard_type_validation():
    """Verify KeyboardTypeParams validates string length and interval."""
    valid = KeyboardTypeParams(text="Hello, JARVIS!", interval=0.05)
    assert valid.text == "Hello, JARVIS!"
    assert valid.interval == 0.05

    # Empty text must be rejected
    with pytest.raises(ValidationError):
        KeyboardTypeParams(text="")

    # Negative interval must be rejected
    with pytest.raises(ValidationError):
        KeyboardTypeParams(text="Valid", interval=-0.1)


def test_keyboard_press_validation():
    """Verify KeyboardPressParams validates single key names."""
    valid = KeyboardPressParams(key="enter")
    assert valid.key == "enter"

    with pytest.raises(ValidationError):
        KeyboardPressParams(key="")


def test_keyboard_hotkey_validation():
    """Verify KeyboardHotkeyParams requires at least 2 keys and cleans them."""
    valid = KeyboardHotkeyParams(keys=["ctrl", "c"])
    assert valid.keys == ["ctrl", "c"]

    # Less than 2 keys must be rejected
    with pytest.raises(ValidationError):
        KeyboardHotkeyParams(keys=["ctrl"])

    # Empty strings in key list must be rejected
    with pytest.raises(ValidationError):
        KeyboardHotkeyParams(keys=["ctrl", "  "])


# -------------------------------------------------------------
# 3. Window Validation Tests
# -------------------------------------------------------------
def test_window_focus_validation():
    """Verify WindowFocusParams requires either handle or title."""
    valid_handle = WindowFocusParams(handle=12345)
    assert valid_handle.handle == 12345
    assert valid_handle.title is None

    valid_title = WindowFocusParams(title="Notepad")
    assert valid_title.handle is None
    assert valid_title.title == "Notepad"

    # Both empty must be rejected
    with pytest.raises(ValidationError):
        WindowFocusParams(handle=None, title=None)

    with pytest.raises(ValidationError):
        WindowFocusParams(handle=None, title="   ")


def test_window_list_validation():
    """Verify WindowListParams defaults."""
    params = WindowListParams()
    assert params.include_invisible is False


# -------------------------------------------------------------
# 4. Application Allowlist Validation Tests
# -------------------------------------------------------------
def test_app_launch_allowlist_enforcement():
    """Verify AppLaunchParams and ApplicationController strictly enforce allowlists."""
    app_ctrl = ApplicationController()

    assert app_ctrl.is_allowlisted("notepad")
    assert app_ctrl.is_allowlisted("calc")
    assert not app_ctrl.is_allowlisted("powershell")
    assert not app_ctrl.is_allowlisted("cmd")

    # Forbidden shell metacharacters in app_name
    with pytest.raises(ValidationError):
        AppLaunchParams(app_name="notepad; rm -rf /")
    with pytest.raises(ValidationError):
        AppLaunchParams(app_name="notepad & echo hacked")
    with pytest.raises(ValidationError):
        AppLaunchParams(app_name="../System32/cmd.exe")

    # Forbidden shell characters in args
    with pytest.raises(ValidationError):
        AppLaunchParams(app_name="notepad", args=["file.txt", "| evil_pipe"])


@pytest.mark.asyncio
async def test_unauthorized_app_rejection():
    """Verify ApplicationController rejects unauthorized apps with PermissionError."""
    app_ctrl = ApplicationController()
    with pytest.raises(PermissionError) as exc_info:
        await app_ctrl.launch(AppLaunchParams(app_name="unauthorized_program"))
    assert "not authorized" in str(exc_info.value)


# -------------------------------------------------------------
# 5. Action Receipt Tests
# -------------------------------------------------------------
def test_receipt_tracker():
    """Verify ReceiptTracker produces valid ActionReceipt with duration."""
    tracker = ReceiptTracker(capability="mouse.click", request_id="req-100")
    with tracker:
        receipt = tracker.create_receipt(success=True, result={"clicked": True})

    assert receipt.capability == "mouse.click"
    assert receipt.request_id == "req-100"
    assert receipt.success is True
    assert receipt.duration_ms >= 0.0
    assert receipt.result == {"clicked": True}
    assert receipt.error is None
