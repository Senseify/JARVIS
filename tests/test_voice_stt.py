"""Tests for Speech-to-Text provider abstraction and deterministic implementation."""

import pytest

from core.voice.audio import AudioInput, create_wav_pcm
from core.voice.stt import DeterministicSTTProvider


@pytest.mark.asyncio
async def test_deterministic_stt_transcription():
    """Verify STT transcription and language parameter handling."""
    provider = DeterministicSTTProvider(default_transcript="Default transcribed command")
    assert await provider.is_available()
    assert provider.provider_name == "deterministic"

    wav = create_wav_pcm(b"\x00\x00" * 4000, sample_rate=16000)
    audio = AudioInput(raw_bytes=wav)

    result = await provider.transcribe(audio, language="en-US")
    assert result.text == "Default transcribed command"
    assert result.confidence == 0.98
    assert result.language == "en-US"
    assert result.duration_seconds == 0.25


@pytest.mark.asyncio
async def test_deterministic_stt_metadata_override():
    """Verify transcription override in metadata (for test injection)."""
    provider = DeterministicSTTProvider()
    wav = create_wav_pcm(b"\x00\x00" * 2000, sample_rate=16000)
    audio = AudioInput(raw_bytes=wav, metadata={"expected_transcript": "Launch notepad"})

    result = await provider.transcribe(audio)
    assert result.text == "Launch notepad"


@pytest.mark.asyncio
async def test_deterministic_stt_simulated_failure():
    """Verify failure handling when STT provider encounters errors."""
    provider = DeterministicSTTProvider(simulate_failure=True)
    assert not await provider.is_available()

    wav = create_wav_pcm(b"\x00\x00" * 1000, sample_rate=16000)
    audio = AudioInput(raw_bytes=wav)

    with pytest.raises(RuntimeError, match="simulated failure"):
        await provider.transcribe(audio)
