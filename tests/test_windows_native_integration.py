"""Real native Windows integration test for desktop automation.

NOTE: This test is designed to be executed strictly on physical or virtual Windows host
environments equipped with a live desktop GUI session. On non-Windows platforms,
this test is skipped cleanly.
"""

import asyncio
import os
import signal
import sys
import pytest

from windows_agent.automation.applications import ApplicationController, AppLaunchParams
from windows_agent.automation.keyboard import KeyboardController, KeyboardTypeParams
from windows_agent.automation.mouse import MouseClickParams, MouseController, MouseMoveParams
from windows_agent.automation.windows import WindowController, WindowFocusParams, WindowListParams
from windows_agent.capabilities import CapabilityRegistry


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Native Windows desktop integration test requires Windows operating system with active GUI session.",
)
@pytest.mark.asyncio
async def test_native_windows_automation_integration():
    """Verify real native Windows computer control sequence:
    1. Launch allowlisted Notepad
    2. Discover Notepad in window.list
    3. Focus Notepad window with window.focus
    4. Move and click mouse inside window
    5. Type text via keyboard
    6. Verify structured action receipts
    7. Clean up process
    """
    registry = CapabilityRegistry()
    launched_pid = None

    try:
        # 1. Application launch using allowlisted 'notepad'
        launch_receipt = await registry.execute("app.launch", {"app_name": "notepad"}, request_id="real-win-launch")
        assert launch_receipt["success"] is True
        assert launch_receipt["app_name"] == "notepad"
        launched_pid = launch_receipt.get("pid")
        assert launched_pid is not None

        # Give Notepad time to create top-level window
        await asyncio.sleep(1.0)

        # 2. Window discovery
        list_receipt = await registry.execute("window.list", {"include_invisible": False}, request_id="real-win-list")
        assert list_receipt["success"] is True
        windows = list_receipt.get("windows", [])
        notepad_windows = [w for w in windows if "notepad" in w.get("title", "").lower() or w.get("process_id") == launched_pid]
        assert len(notepad_windows) > 0, f"Notepad window not found in enumerated windows: {windows}"

        target_hwnd = notepad_windows[0]["handle"]

        # 3. Window focus
        focus_receipt = await registry.execute("window.focus", {"handle": target_hwnd}, request_id="real-win-focus")
        assert focus_receipt["success"] is True
        assert focus_receipt["focused"] is True

        await asyncio.sleep(0.3)

        # 4. Mouse movement and click
        move_receipt = await registry.execute("mouse.move", {"x": 300, "y": 300, "duration": 0.1}, request_id="real-win-move")
        assert move_receipt["success"] is True

        click_receipt = await registry.execute("mouse.click", {"x": 300, "y": 300, "button": "left"}, request_id="real-win-click")
        assert click_receipt["success"] is True

        # 5. Keyboard input
        type_receipt = await registry.execute(
            "keyboard.type",
            {"text": "JARVIS Native Automation Verification", "interval": 0.02},
            request_id="real-win-type",
        )
        assert type_receipt["success"] is True
        assert type_receipt["chars_typed"] == len("JARVIS Native Automation Verification")

    finally:
        # 7. Clean up launched Notepad process
        if launched_pid:
            try:
                os.kill(launched_pid, signal.SIGTERM)
            except Exception:
                pass


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Native Windows desktop integration test requires Windows operating system with active GUI session.",
)
@pytest.mark.asyncio
async def test_native_windows_screen_capture_and_verification():
    """Verify real native Windows screen capture and Action -> Observe -> Verify execution:
    1. Perform real screen.capture
    2. Check valid screen dimensions and temporary observation file
    3. Launch Notepad with action.verify checking window_exists
    4. Focus Notepad with action.verify checking active_window_title
    5. Terminate Notepad
    """
    registry = CapabilityRegistry()
    launched_pid = None

    try:
        # 1. Real screen capture
        cap_res = await registry.execute("screen.capture", {}, request_id="real-win-cap")
        assert cap_res["success"] is True
        assert cap_res["width"] > 0
        assert cap_res["height"] > 0
        assert cap_res["file_path"] is not None
        assert os.path.exists(cap_res["file_path"])
        assert cap_res["metadata"]["is_windows"] is True

        # 2. Action -> Observe -> Verify: Launch Notepad and verify window_exists
        verify_launch = await registry.execute(
            "action.verify",
            {
                "action_capability": "app.launch",
                "action_parameters": {"app_name": "notepad"},
                "expected_condition": "window_exists",
                "expected_value": "notepad",
                "pre_observe": True,
            },
            request_id="real-win-act-ver-launch",
        )
        assert verify_launch["success"] is True
        assert verify_launch["verified"] is True
        launched_pid = verify_launch["action_receipt"].get("pid")

        await asyncio.sleep(0.5)

        # 3. Action -> Observe -> Verify: Focus Notepad and verify active_window_title
        verify_focus = await registry.execute(
            "action.verify",
            {
                "action_capability": "window.focus",
                "action_parameters": {"title": "Notepad"},
                "expected_condition": "active_window_title",
                "expected_value": "Notepad",
                "pre_observe": False,
            },
            request_id="real-win-act-ver-focus",
        )
        assert verify_focus["success"] is True
        assert verify_focus["verified"] is True

    finally:
        if launched_pid:
            try:
                os.kill(launched_pid, signal.SIGTERM)
            except Exception:
                pass
