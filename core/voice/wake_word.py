"""Wake Word Detection and Voice State Management for JARVIS OS.

Provides optional wake word activation ('JARVIS'), voice pipeline state tracking,
and audio interruption/cancellation hooks with zero continuous audio recording leaks.
"""

from __future__ import annotations

from enum import Enum
import logging
import re
import time
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VoiceState(str, Enum):
    """Voice interaction state lifecycle."""

    IDLE = "idle"
    WAKE_DETECTED = "wake_detected"
    LISTENING = "listening"
    UNDERSTANDING = "understanding"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class WakeWordConfig(BaseModel):
    """Configuration for wake word activation."""

    enabled: bool = True
    wake_words: list[str] = Field(default_factory=lambda: ["jarvis", "hey jarvis"])
    require_exact_prefix: bool = False
    cooldown_seconds: float = 1.0


class WakeWordResult(BaseModel):
    """Result of wake-word evaluation on incoming audio or transcript."""

    detected: bool = False
    cleaned_command: str = ""
    wake_word_matched: str | None = None
    confidence: float = 1.0


class WakeWordDetector:
    """Evaluates transcripts or audio frames for the wake word 'JARVIS'."""

    def __init__(self, config: WakeWordConfig | None = None) -> None:
        self.config = config or WakeWordConfig()
        self._last_trigger_time: float = 0.0

    def evaluate(self, transcript: str) -> WakeWordResult:
        """Evaluate a transcript for wake words and strip the prefix if found."""
        if not self.config.enabled:
            return WakeWordResult(detected=True, cleaned_command=transcript.strip())

        cleaned = transcript.strip().lower()
        now = time.time()
        for w in self.config.wake_words:
            w_lower = w.lower()
            # Match word boundary
            pattern = rf"^\b{re.escape(w_lower)}\b[\s,:\-]*"
            match = re.search(pattern, cleaned)
            if match:
                remainder = transcript[match.end():].strip()
                self._last_trigger_time = now
                return WakeWordResult(
                    detected=True,
                    cleaned_command=remainder,
                    wake_word_matched=w,
                    confidence=1.0,
                )

        return WakeWordResult(detected=False, cleaned_command=transcript.strip())


class VoiceInterruptionController:
    """Coordinates voice cancellation and interruption when new speech is detected."""

    def __init__(self) -> None:
        self._is_speaking: bool = False
        self._current_speech_id: str | None = None

    def start_speaking(self, speech_id: str) -> None:
        """Mark TTS output as currently speaking."""
        self._is_speaking = True
        self._current_speech_id = speech_id

    def stop_speaking(self) -> None:
        """Mark TTS output as finished."""
        self._is_speaking = False
        self._current_speech_id = None

    def interrupt(self) -> bool:
        """Trigger an interruption if JARVIS is currently speaking."""
        if self._is_speaking:
            logger.info("Voice interruption triggered for speech_id: %s", self._current_speech_id)
            self._is_speaking = False
            self._current_speech_id = None
            return True
        return False

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking
