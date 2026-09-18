"""Tests for Phase 5 verification engine and deterministic verification primitives."""

import pytest
from pydantic import ValidationError

from windows_agent.observation.models import (
    ActionVerifyParams,
    ScreenState,
    VerificationResult,
)
from windows_agent.observation.verifier import VerificationEngine


def test_verification_result_model():
    """Verify VerificationResult model fields and serialization."""
    res = VerificationResult(
        check_type="window_exists",
        expected_condition="Window Notepad exists",
        observed_state=["Notepad - Untitled"],
        passed=True,
    )
    assert res.passed is True
    assert res.failure_reason is None
    assert res.verification_id is not None
    assert res.timestamp is not None

    dumped = res.model_dump()
    assert dumped["passed"] is True
    assert dumped["check_type"] == "window_exists"


def test_action_verify_params_validation():
    """Verify ActionVerifyParams validation."""
    params = ActionVerifyParams(
        action_capability="mouse.move",
        action_parameters={"x": 100, "y": 200},
        expected_condition="screen_dimensions",
        expected_value=640,
        pre_observe=True,
    )
    assert params.action_capability == "mouse.move"
    assert params.pre_observe is True

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        ActionVerifyParams(
            action_capability="mouse.move",
            expected_condition="screen_dimensions",
            expected_value=640,
            invalid_extra_param="rejected",
        )


def test_verify_active_window_title():
    """Verify active window title matching and failure reporting."""
    engine = VerificationEngine()

    state = ScreenState(
        width=1920,
        height=1080,
        active_window={"title": "Visual Studio Code - JARVIS", "handle": 101},
    )

    # Substring match (default)
    res_sub = engine.verify_active_window_title(state, "Visual Studio Code")
    assert res_sub.passed is True
    assert res_sub.failure_reason is None

    # Case insensitive match
    res_ci = engine.verify_active_window_title(state, "visual studio code")
    assert res_ci.passed is True

    # Exact match - mismatch
    res_exact_fail = engine.verify_active_window_title(state, "Visual Studio Code", exact=True)
    assert res_exact_fail.passed is False
    assert "does not match expected" in res_exact_fail.failure_reason

    # Substring mismatch
    res_fail = engine.verify_active_window_title(state, "Calculator")
    assert res_fail.passed is False
    assert res_fail.failure_reason is not None
    assert "Calculator" in res_fail.failure_reason


def test_verify_window_exists():
    """Verify window existence checks against enumerated window lists."""
    engine = VerificationEngine()
    window_list = [
        {"title": "Untitled - Notepad", "handle": 201, "is_visible": True},
        {"title": "Command Prompt", "handle": 202, "is_visible": True},
        {"title": "Background Worker", "handle": 203, "is_visible": False},
    ]

    # Found
    res = engine.verify_window_exists(window_list, "Notepad")
    assert res.passed is True
    assert "Untitled - Notepad" in res.observed_state

    # Not found
    res_missing = engine.verify_window_exists(window_list, "Calculator")
    assert res_missing.passed is False
    assert "No window containing 'Calculator' found" in res_missing.failure_reason


def test_verify_window_is_visible():
    """Verify window visibility checking."""
    engine = VerificationEngine()
    window_list = [
        {"title": "Active Document", "handle": 301, "is_visible": True},
        {"title": "Hidden Task", "handle": 302, "is_visible": False},
    ]

    # Exists and visible
    res_vis = engine.verify_window_is_visible(window_list, "Active Document")
    assert res_vis.passed is True

    # Exists but not visible
    res_invis = engine.verify_window_is_visible(window_list, "Hidden Task")
    assert res_invis.passed is False
    assert "exists but is not visible" in res_invis.failure_reason

    # Does not exist
    res_absent = engine.verify_window_is_visible(window_list, "NonExistent")
    assert res_absent.passed is False
    assert "does not exist" in res_absent.failure_reason


def test_verify_window_disappeared():
    """Verify check confirming window was closed or removed."""
    engine = VerificationEngine()
    window_list = [
        {"title": "Persistent Window", "handle": 401, "is_visible": True},
    ]

    # Disappeared (not present)
    res_closed = engine.verify_window_disappeared(window_list, "TerminatedApp")
    assert res_closed.passed is True

    # Still exists
    res_still_there = engine.verify_window_disappeared(window_list, "Persistent")
    assert res_still_there.passed is False
    assert "still exists" in res_still_there.failure_reason


def test_verify_screen_dimensions():
    """Verify screen resolution checks."""
    engine = VerificationEngine()

    state_valid = ScreenState(width=1920, height=1080)
    res_ok = engine.verify_screen_dimensions(state_valid, min_width=1024, min_height=768)
    assert res_ok.passed is True

    state_small = ScreenState(width=320, height=240)
    res_fail = engine.verify_screen_dimensions(state_small, min_width=640, min_height=480)
    assert res_fail.passed is False
    assert "below minimum" in res_fail.failure_reason


def test_verify_condition_dispatch():
    """Verify generic condition dispatcher."""
    engine = VerificationEngine()
    state = ScreenState(
        width=1920,
        height=1080,
        active_window={"title": "Terminal Window", "handle": 501},
    )
    window_list = [{"title": "Terminal Window", "handle": 501, "is_visible": True}]

    # active_window_title
    res1 = engine.verify_condition("active_window_title", "Terminal", screen_state=state)
    assert res1.passed is True

    # window_exists
    res2 = engine.verify_condition("window_exists", "Terminal", window_list=window_list)
    assert res2.passed is True

    # window_visible
    res3 = engine.verify_condition("window_visible", "Terminal", window_list=window_list)
    assert res3.passed is True

    # window_disappeared
    res4 = engine.verify_condition("window_disappeared", "Calculator", window_list=window_list)
    assert res4.passed is True

    # screen_dimensions
    res5 = engine.verify_condition("screen_dimensions", 640, screen_state=state)
    assert res5.passed is True

    # Missing state error
    with pytest.raises(ValueError):
        engine.verify_condition("active_window_title", "Terminal")

    # Missing window_list error
    with pytest.raises(ValueError):
        engine.verify_condition("window_exists", "Terminal")

    # Unknown condition
    with pytest.raises(ValueError, match="Unknown verification condition"):
        engine.verify_condition("completely_unknown_check", "value")
