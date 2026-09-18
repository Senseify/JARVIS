"""Audio abstraction layer separating audio byte representations from STT and TTS engines."""

import base64
import io
from typing import Any, Dict, Optional
import wave

from core.models.voice import AudioFormat


class AudioInput:
    """Encapsulates input audio data for speech recognition and processing."""

    def __init__(
        self,
        raw_bytes: bytes,
        format: AudioFormat = AudioFormat.WAV,
        sample_rate: int = 16000,
        channels: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not raw_bytes:
            raise ValueError("raw_bytes cannot be empty.")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive.")
        if channels not in (1, 2):
            raise ValueError("channels must be 1 (mono) or 2 (stereo).")

        self.raw_bytes = raw_bytes
        self.format = format
        self.sample_rate = sample_rate
        self.channels = channels
        self.metadata = metadata or {}

    @classmethod
    def from_base64(
        cls,
        audio_base64: str,
        format: AudioFormat = AudioFormat.WAV,
        sample_rate: int = 16000,
        channels: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "AudioInput":
        """Construct an AudioInput instance from a base64-encoded string."""
        if not audio_base64 or not audio_base64.strip():
            raise ValueError("audio_base64 string cannot be empty.")
        try:
            raw_bytes = base64.b64decode(audio_base64)
        except Exception as e:
            raise ValueError(f"Invalid base64 audio payload: {e}")
        return cls(
            raw_bytes=raw_bytes,
            format=format,
            sample_rate=sample_rate,
            channels=channels,
            metadata=metadata,
        )

    def to_base64(self) -> str:
        """Encode audio bytes as a base64 string."""
        return base64.b64encode(self.raw_bytes).decode("ascii")

    @property
    def byte_length(self) -> int:
        return len(self.raw_bytes)

    @property
    def duration_seconds(self) -> float:
        """Estimate duration in seconds from WAV header or raw PCM byte count."""
        if self.format == AudioFormat.WAV and self.raw_bytes.startswith(b"RIFF"):
            try:
                with wave.open(io.BytesIO(self.raw_bytes), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate > 0:
                        return round(frames / float(rate), 3)
            except Exception:
                pass
        # Fallback approximation assuming 16-bit PCM (2 bytes per sample)
        bytes_per_second = self.sample_rate * self.channels * 2
        if bytes_per_second > 0:
            return round(len(self.raw_bytes) / float(bytes_per_second), 3)
        return 0.0


class AudioOutput:
    """Encapsulates generated or synthesized audio output."""

    def __init__(
        self,
        raw_bytes: bytes,
        format: AudioFormat = AudioFormat.WAV,
        sample_rate: int = 16000,
        channels: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not raw_bytes:
            raise ValueError("raw_bytes cannot be empty.")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive.")
        if channels not in (1, 2):
            raise ValueError("channels must be 1 (mono) or 2 (stereo).")

        self.raw_bytes = raw_bytes
        self.format = format
        self.sample_rate = sample_rate
        self.channels = channels
        self.metadata = metadata or {}

    def to_base64(self) -> str:
        """Encode output audio bytes as a base64 string."""
        return base64.b64encode(self.raw_bytes).decode("ascii")

    @property
    def byte_length(self) -> int:
        return len(self.raw_bytes)

    @property
    def duration_seconds(self) -> float:
        """Calculate duration from WAV header or 16-bit PCM byte count."""
        if self.format == AudioFormat.WAV and self.raw_bytes.startswith(b"RIFF"):
            try:
                with wave.open(io.BytesIO(self.raw_bytes), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate > 0:
                        return round(frames / float(rate), 3)
            except Exception:
                pass
        bytes_per_second = self.sample_rate * self.channels * 2
        if bytes_per_second > 0:
            return round(len(self.raw_bytes) / float(bytes_per_second), 3)
        return 0.0


def create_wav_pcm(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width_bytes: int = 2,
) -> bytes:
    """Pack raw PCM samples into a compliant WAV byte stream using the standard wave library."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width_bytes)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buffer.getvalue()
