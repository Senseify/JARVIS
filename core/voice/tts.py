"""Text-to-Speech (TTS) provider interface and deterministic implementations."""

from abc import ABC, abstractmethod
import base64
from datetime import datetime, timezone
import logging
import math
import struct
from typing import Optional

from core.models.voice import AudioFormat, SpeechSynthesisRequest, SpeechSynthesisResult
from core.voice.audio import create_wav_pcm

logger = logging.getLogger(__name__)


class BaseTTSProvider(ABC):
    """Abstract interface for Text-to-Speech synthesis engines."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier name for this TTS provider."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider is operational and ready to synthesize audio."""
        pass

    @abstractmethod
    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        """Synthesize supplied text into structured audio output."""
        pass


class DeterministicTTSProvider(BaseTTSProvider):
    """Deterministic TTS provider generating genuine, valid WAV PCM audio byte streams.

    Guarantees no fake success when audio cannot be generated.
    """

    def __init__(self, simulate_failure: bool = False):
        self.simulate_failure = simulate_failure

    @property
    def provider_name(self) -> str:
        return "deterministic"

    async def is_available(self) -> bool:
        return not self.simulate_failure

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        if self.simulate_failure:
            raise RuntimeError("Deterministic TTS provider simulated failure.")

        sample_rate = 16000
        # Calculate proportional duration based on text length and speed
        char_count = len(request.text.strip())
        # Roughly ~15-20 characters per second of speech
        raw_duration = max(0.2, (char_count / 15.0) / request.speed)
        duration = round(min(raw_duration, 10.0), 3)

        num_samples = int(sample_rate * duration)
        freq = 440.0 * request.pitch  # Base concert A frequency modulated by pitch

        # Generate smooth sinusoidal 16-bit PCM samples with gentle envelope to avoid clicks
        pcm_chunks = []
        amplitude = 8000  # Conservative amplitude within int16 bounds (-32768 to 32767)

        for i in range(num_samples):
            t = float(i) / sample_rate
            # Apply fade in/out envelope
            env = min(1.0, float(i) / 1000.0) if i < 1000 else (min(1.0, float(num_samples - i) / 1000.0) if i > num_samples - 1000 else 1.0)
            sample_val = int(amplitude * env * math.sin(2.0 * math.pi * freq * t))
            pcm_chunks.append(struct.pack("<h", sample_val))

        raw_pcm = b"".join(pcm_chunks)
        wav_bytes = create_wav_pcm(
            pcm_bytes=raw_pcm,
            sample_rate=sample_rate,
            channels=1,
            sample_width_bytes=2,
        )

        b64_audio = base64.b64encode(wav_bytes).decode("ascii")

        return SpeechSynthesisResult(
            audio_base64=b64_audio,
            audio_bytes_length=len(wav_bytes),
            format=AudioFormat.WAV,
            duration_seconds=duration,
            sample_rate=sample_rate,
            provider=self.provider_name,
            metadata={
                "text_length": char_count,
                "speed": request.speed,
                "pitch": request.pitch,
                "language": request.language,
                "voice_id": request.voice_id or "default",
            },
            timestamp=datetime.now(timezone.utc),
        )
