"""Tests for JARVIS OS Voice Command models."""

import pytest
from pydantic import ValidationError

from core.models.voice_command import (
    VoiceCommand,
    VoiceCommandIntent,
    VoiceCommandIntentType,
    VoiceCommandRequest,
    VoiceCommandResult,
)


def test_voice_command_intent_model():
    """Verify VoiceCommandIntent validation and constraints."""
    intent = VoiceCommandIntent(
        intent_type=VoiceCommandIntentType.APP_LAUNCH,
        action_target="notepad",
        parameters={"app_name": "notepad", "window_title": "Notepad"},
        confidence=1.0,
        matched_pattern="app_launch",
    )
    assert intent.intent_type == VoiceCommandIntentType.APP_LAUNCH
    assert intent.action_target == "notepad"
    assert intent.confidence == 1.0

    # Extra fields rejected
    with pytest.raises(ValidationError):
        VoiceCommandIntent(
            intent_type=VoiceCommandIntentType.APP_LAUNCH,
            action_target="notepad",
            unknown_arg="invalid",
        )


def test_voice_command_model():
    """Verify VoiceCommand creation."""
    cmd = VoiceCommand(
        transcript="open notepad",
        intent=VoiceCommandIntent(
            intent_type=VoiceCommandIntentType.APP_LAUNCH,
            action_target="notepad",
        ),
        task_id="task_123",
    )
    assert cmd.transcript == "open notepad"
    assert cmd.intent.intent_type == VoiceCommandIntentType.APP_LAUNCH
    assert cmd.task_id == "task_123"


def test_voice_command_result_model():
    """Verify VoiceCommandResult structure."""
    res = VoiceCommandResult(
        command_id="cmd_999",
        transcript="type hello",
        intent=VoiceCommandIntent(
            intent_type=VoiceCommandIntentType.KEYBOARD_TYPE,
            action_target="hello",
        ),
        status="completed",
        success=True,
        response_text="Done. The text was entered.",
        synthesized_audio="UklGRgAAAABXQVZF",
        verification_status="verified",
        duration_ms=120.5,
    )
    assert res.success is True
    assert res.verification_status == "verified"
    assert res.duration_ms == 120.5


def test_voice_command_request_model():
    """Verify VoiceCommandRequest with text_override and defaults."""
    req = VoiceCommandRequest(text_override="click")
    assert req.text_override == "click"
    assert req.synthesize_response is True
