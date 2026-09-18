"""Tests for JARVIS OS Voice Foundation data models."""

import pytest
from pydantic import ValidationError

from core.models.voice import (
    AudioFormat,
    SpeechRecognitionResult,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    VoiceInput,
    VoiceState,
)


def test_voice_input_validation():
    """Verify VoiceInput schema validation, constraints, and defaults."""
    valid = VoiceInput(
        audio_base64="UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
        format=AudioFormat.WAV,
        sample_rate=16000,
        channels=1,
    )
    assert valid.sample_rate == 16000
    assert valid.channels == 1
    assert valid.format == AudioFormat.WAV

    # Rejection of empty audio_base64
    with pytest.raises(ValidationError):
        VoiceInput(audio_base64="   ")

    # Rejection of invalid sample rate
    with pytest.raises(ValidationError):
        VoiceInput(audio_base64="AAAA", sample_rate=-100)

    # Rejection of invalid channel count
    with pytest.raises(ValidationError):
        VoiceInput(audio_base64="AAAA", channels=4)


def test_speech_recognition_result_model():
    """Verify SpeechRecognitionResult structure and defaults."""
    result = SpeechRecognitionResult(
        text="Open notepad",
        confidence=0.95,
        language="en-US",
        duration_seconds=1.5,
        provider="deterministic",
    )
    assert result.text == "Open notepad"
    assert result.confidence == 0.95
    assert result.is_final is True

    # Rejection of confidence out of bounds
    with pytest.raises(ValidationError):
        SpeechRecognitionResult(text="Test", confidence=1.5)


def test_speech_synthesis_request_model():
    """Verify SpeechSynthesisRequest validation, constraints, and extra field rejection."""
    req = SpeechSynthesisRequest(
        text="Hello world",
        language="en-US",
        speed=1.2,
        pitch=0.9,
    )
    assert req.text == "Hello world"
    assert req.speed == 1.2
    assert req.pitch == 0.9

    # Rejection of empty text
    with pytest.raises(ValidationError):
        SpeechSynthesisRequest(text="   ")

    # Rejection of negative speed
    with pytest.raises(ValidationError):
        SpeechSynthesisRequest(text="Valid", speed=-0.5)

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        SpeechSynthesisRequest(text="Valid", unexpected_param=True)


def test_speech_synthesis_result_model():
    """Verify SpeechSynthesisResult validation."""
    res = SpeechSynthesisResult(
        audio_base64="UklGRgAAAABXQVZF",
        audio_bytes_length=12,
        format=AudioFormat.WAV,
        duration_seconds=0.5,
        sample_rate=16000,
    )
    assert res.audio_bytes_length == 12
    assert res.duration_seconds == 0.5


def test_voice_state_model():
    """Verify VoiceState status and default flags."""
    state = VoiceState()
    assert state.status == "ready"
    assert not state.is_listening
    assert not state.is_speaking
    assert state.current_stt_provider == "deterministic"
    assert state.current_tts_provider == "deterministic"
