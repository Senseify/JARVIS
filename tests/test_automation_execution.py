"""Tests for CapabilityRegistry execution of desktop automation capabilities."""

import pytest
from windows_agent.capabilities import CapabilityRegistry


@pytest.fixture
def registry():
    return CapabilityRegistry()


@pytest.mark.asyncio
async def test_mouse_move_execution(registry):
    """Verify mouse.move executes and returns action receipt."""
    receipt = await registry.execute("mouse.move", {"x": 200, "y": 150, "duration": 0.1}, request_id="req-m1")

    assert receipt["capability"] == "mouse.move"
    assert receipt["request_id"] == "req-m1"
    assert receipt["success"] is True
    assert receipt["duration_ms"] >= 0.0
    assert receipt["x"] == 200
    assert receipt["y"] == 150


@pytest.mark.asyncio
async def test_mouse_click_execution(registry):
    """Verify mouse.click executes and returns action receipt."""
    receipt = await registry.execute("mouse.click", {"x": 50, "y": 50, "button": "left", "clicks": 1})

    assert receipt["capability"] == "mouse.click"
    assert receipt["success"] is True
    assert receipt["button"] == "left"
    assert receipt["clicks"] == 1


@pytest.mark.asyncio
async def test_mouse_double_click_execution(registry):
    """Verify mouse.double_click executes."""
    receipt = await registry.execute("mouse.double_click", {"button": "left"})

    assert receipt["capability"] == "mouse.double_click"
    assert receipt["success"] is True
    assert receipt["clicks"] == 2


@pytest.mark.asyncio
async def test_keyboard_type_execution(registry):
    """Verify keyboard.type executes and reports chars typed."""
    receipt = await registry.execute("keyboard.type", {"text": "Testing JARVIS", "interval": 0.0})

    assert receipt["capability"] == "keyboard.type"
    assert receipt["success"] is True
    assert receipt["chars_typed"] == len("Testing JARVIS")


@pytest.mark.asyncio
async def test_keyboard_hotkey_execution(registry):
    """Verify keyboard.hotkey executes."""
    receipt = await registry.execute("keyboard.hotkey", {"keys": ["ctrl", "v"]})

    assert receipt["capability"] == "keyboard.hotkey"
    assert receipt["success"] is True
    assert receipt["keys"] == ["ctrl", "v"]


@pytest.mark.asyncio
async def test_window_list_execution(registry):
    """Verify window.list returns structured window information."""
    receipt = await registry.execute("window.list", {"include_invisible": False})

    assert receipt["capability"] == "window.list"
    assert receipt["success"] is True
    assert "windows" in receipt
    assert isinstance(receipt["windows"], list)


@pytest.mark.asyncio
async def test_app_launch_allowlist_execution(registry):
    """Verify app.launch executes for allowlisted apps."""
    receipt = await registry.execute("app.launch", {"app_name": "notepad"})

    assert receipt["capability"] == "app.launch"
    assert receipt["success"] is True
    assert receipt["app_name"] == "notepad"
    assert "executable" in receipt


@pytest.mark.asyncio
async def test_app_launch_unallowlisted_rejection(registry):
    """Verify app.launch raises RuntimeError for unallowlisted apps."""
    with pytest.raises(RuntimeError) as exc_info:
        await registry.execute("app.launch", {"app_name": "cmd"})
    assert "not authorized" in str(exc_info.value)


@pytest.mark.asyncio
async def test_malformed_parameter_validation_error(registry):
    """Verify malformed parameters raise ValueError before reaching handler."""
    with pytest.raises(ValueError) as exc_info:
        await registry.execute("mouse.move", {"x": -50, "y": 100})
    assert "Invalid parameters" in str(exc_info.value)
