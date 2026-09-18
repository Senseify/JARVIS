"""Speech-to-Text (STT) provider interface and deterministic implementations."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
from typing import Dict, Optional

from core.models.voice import SpeechRecognitionResult
from core.voice.audio import AudioInput

logger = logging.getLogger(__name__)


class BaseSTTProvider(ABC):
    """Abstract interface for Speech-to-Text transcription engines."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier name for this STT provider."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider is operational and ready to process audio."""
        pass

    @abstractmethod
    async def transcribe(
        self,
        audio: AudioInput,
        language: Optional[str] = None,
    ) -> SpeechRecognitionResult:
        """Transcribe provided audio into structured speech recognition result."""
        pass


class DeterministicSTTProvider(BaseSTTProvider):
    """Deterministic, zero-dependency STT provider for offline verification and testing."""

    def __init__(
        self,
        default_transcript: str = "Deterministic transcription result",
        canned_transcripts: Optional[Dict[str, str]] = None,
        simulate_failure: bool = False,
    ):
        self._default_transcript = default_transcript
        self._canned_transcripts = canned_transcripts or {}
        self.simulate_failure = simulate_failure

    @property
    def provider_name(self) -> str:
        return "deterministic"

    async def is_available(self) -> bool:
        return not self.simulate_failure

    async def transcribe(
        self,
        audio: AudioInput,
        language: Optional[str] = None,
    ) -> SpeechRecognitionResult:
        if self.simulate_failure:
            raise RuntimeError("Deterministic STT provider simulated failure.")

        lang = language or "en-US"

        # Check metadata for explicit transcription override (useful for testing)
        override = audio.metadata.get("expected_transcript") or audio.metadata.get("transcript")
        if override:
            text = str(override)
        else:
            # Check canned transcripts by byte length or audio hash
            key = f"{audio.byte_length}_{lang}"
            text = self._canned_transcripts.get(key, self._default_transcript)

        duration = audio.duration_seconds

        return SpeechRecognitionResult(
            text=text,
            confidence=0.98,
            language=lang,
            duration_seconds=duration,
            is_final=True,
            provider=self.provider_name,
            metadata={
                "byte_length": audio.byte_length,
                "format": audio.format.value,
                "sample_rate": audio.sample_rate,
            },
            timestamp=datetime.now(timezone.utc),
        )
