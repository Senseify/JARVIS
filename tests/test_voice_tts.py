"""Tests for Text-to-Speech provider abstraction and deterministic audio synthesis."""

import base64
import pytest
import wave
import io

from core.models.voice import AudioFormat, SpeechSynthesisRequest
from core.voice.tts import DeterministicTTSProvider


@pytest.mark.asyncio
async def test_deterministic_tts_generates_real_audio():
    """Verify that DeterministicTTSProvider generates genuine, decodable WAV audio bytes."""
    provider = DeterministicTTSProvider()
    assert await provider.is_available()
    assert provider.provider_name == "deterministic"

    req = SpeechSynthesisRequest(
        text="JARVIS system initialization complete.",
        speed=1.0,
        pitch=1.0,
    )

    result = await provider.synthesize(req)
    assert result.format == AudioFormat.WAV
    assert result.duration_seconds > 0.0
    assert result.audio_bytes_length > 0

    # Verify bytes are valid WAV
    decoded_bytes = base64.b64decode(result.audio_base64)
    assert len(decoded_bytes) == result.audio_bytes_length
    assert decoded_bytes.startswith(b"RIFF")

    # Verify standard wave library can read and parse the generated audio
    with wave.open(io.BytesIO(decoded_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() > 0


@pytest.mark.asyncio
async def test_deterministic_tts_simulated_failure():
    """Verify failure handling in TTS provider."""
    provider = DeterministicTTSProvider(simulate_failure=True)
    assert not await provider.is_available()

    req = SpeechSynthesisRequest(text="Should fail")
    with pytest.raises(RuntimeError, match="simulated failure"):
        await provider.synthesize(req)
