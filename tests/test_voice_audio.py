"""Tests for JARVIS OS AudioInput, AudioOutput, and WAV packing utilities."""

import pytest

from core.models.voice import AudioFormat
from core.voice.audio import AudioInput, AudioOutput, create_wav_pcm


def test_audio_input_base64_roundtrip():
    """Verify AudioInput base64 encoding and decoding."""
    raw_sample = b"\x00\x00\x10\x00\x20\x00\x30\x00"
    audio = AudioInput(raw_bytes=raw_sample, format=AudioFormat.PCM, sample_rate=16000, channels=1)

    b64_str = audio.to_base64()
    reconstructed = AudioInput.from_base64(b64_str, format=AudioFormat.PCM, sample_rate=16000, channels=1)

    assert reconstructed.raw_bytes == raw_sample
    assert reconstructed.byte_length == 8

    # Rejection of invalid base64
    with pytest.raises(ValueError, match="Invalid base64"):
        AudioInput.from_base64("!!!not_base64!!!")


def test_create_wav_pcm_generates_valid_riff_header():
    """Verify that create_wav_pcm constructs a valid WAV file structure."""
    pcm_data = b"\x00\x00" * 8000  # 0.5s of mono 16-bit silence at 16kHz
    wav_bytes = create_wav_pcm(pcm_bytes=pcm_data, sample_rate=16000, channels=1, sample_width_bytes=2)

    assert wav_bytes.startswith(b"RIFF")
    assert b"WAVE" in wav_bytes[:16]
    assert len(wav_bytes) > len(pcm_data)  # Contains headers + data

    audio = AudioInput(raw_bytes=wav_bytes, format=AudioFormat.WAV)
    assert audio.duration_seconds == 0.5


def test_audio_output_attributes():
    """Verify AudioOutput properties."""
    raw_sample = b"RIFF....WAVEfmt ...."
    output = AudioOutput(raw_bytes=raw_sample, format=AudioFormat.WAV)
    assert output.byte_length == len(raw_sample)
    assert isinstance(output.to_base64(), str)
