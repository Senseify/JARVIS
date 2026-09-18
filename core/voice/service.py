"""VoiceService orchestrating STT, TTS, audio abstractions, and EventBus notifications."""

import logging
from typing import Optional

from core.constants import EventType
from core.events.bus import EventBus
from core.models.events import AgentEvent
from core.models.voice import (
    SpeechRecognitionResult,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    VoiceInput,
    VoiceState,
)
from core.voice.audio import AudioInput
from core.voice.stt import BaseSTTProvider, DeterministicSTTProvider
from core.voice.tts import BaseTTSProvider, DeterministicTTSProvider

logger = logging.getLogger(__name__)


class VoiceService:
    """High-level voice subsystem orchestrator coordinating speech recognition, synthesis, and lifecycle events."""

    def __init__(
        self,
        stt_provider: Optional[BaseSTTProvider] = None,
        tts_provider: Optional[BaseTTSProvider] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self.stt_provider = stt_provider or DeterministicSTTProvider()
        self.tts_provider = tts_provider or DeterministicTTSProvider()
        self.event_bus = event_bus

        self._state = VoiceState(
            status="ready",
            is_listening=False,
            is_speaking=False,
            current_stt_provider=self.stt_provider.provider_name,
            current_tts_provider=self.tts_provider.provider_name,
        )

    async def get_status(self) -> VoiceState:
        """Inspect and return the current status of the voice subsystem."""
        stt_avail = await self.stt_provider.is_available()
        tts_avail = await self.tts_provider.is_available()

        status_label = "ready"
        if not stt_avail or not tts_avail:
            status_label = "degraded"
        elif self._state.is_listening:
            status_label = "transcribing"
        elif self._state.is_speaking:
            status_label = "synthesizing"

        self._state.status = status_label
        self._state.metadata = {
            "stt_available": stt_avail,
            "tts_available": tts_avail,
            "stt_provider": self.stt_provider.provider_name,
            "tts_provider": self.tts_provider.provider_name,
        }
        return self._state

    async def transcribe(self, voice_input: VoiceInput) -> SpeechRecognitionResult:
        """Process input audio payload and return structured transcription result."""
        # 1. Parse and validate audio payload
        audio = AudioInput.from_base64(
            audio_base64=voice_input.audio_base64,
            format=voice_input.format,
            sample_rate=voice_input.sample_rate,
            channels=voice_input.channels,
            metadata=voice_input.metadata,
        )

        # 2. Emit VOICE_INPUT_RECEIVED
        await self._publish_event(
            event_type=EventType.VOICE_INPUT_RECEIVED,
            payload={
                "byte_length": audio.byte_length,
                "format": audio.format.value,
                "sample_rate": audio.sample_rate,
                "channels": audio.channels,
            },
        )

        self._state.is_listening = True
        self._state.status = "transcribing"

        try:
            language = voice_input.metadata.get("language")
            result = await self.stt_provider.transcribe(audio, language=language)

            self._state.last_transcription = result.text
            self._state.is_listening = False
            self._state.status = "ready"

            # 3. Emit VOICE_TRANSCRIPTION_COMPLETED
            await self._publish_event(
                event_type=EventType.VOICE_TRANSCRIPTION_COMPLETED,
                payload={
                    "text": result.text,
                    "confidence": result.confidence,
                    "language": result.language,
                    "duration_seconds": result.duration_seconds,
                    "provider": result.provider,
                },
            )
            return result

        except Exception as e:
            self._state.is_listening = False
            self._state.status = "error"
            await self._publish_event(
                event_type=EventType.VOICE_ERROR,
                payload={"stage": "transcription", "error": str(e)},
                error=str(e),
            )
            logger.error(f"Voice transcription failed: {e}")
            raise

    async def speak(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        """Synthesize text into speech audio bytes and return structured synthesis result."""
        self._state.is_speaking = True
        self._state.status = "synthesizing"

        # 1. Emit VOICE_SYNTHESIS_STARTED
        await self._publish_event(
            event_type=EventType.VOICE_SYNTHESIS_STARTED,
            payload={
                "text_length": len(request.text),
                "language": request.language,
                "speed": request.speed,
                "pitch": request.pitch,
            },
        )

        try:
            result = await self.tts_provider.synthesize(request)

            self._state.last_synthesized_text = request.text
            self._state.is_speaking = False
            self._state.status = "ready"

            # 2. Emit VOICE_SYNTHESIS_COMPLETED
            await self._publish_event(
                event_type=EventType.VOICE_SYNTHESIS_COMPLETED,
                payload={
                    "duration_seconds": result.duration_seconds,
                    "audio_bytes_length": result.audio_bytes_length,
                    "format": result.format.value,
                    "provider": result.provider,
                },
            )
            return result

        except Exception as e:
            self._state.is_speaking = False
            self._state.status = "error"
            await self._publish_event(
                event_type=EventType.VOICE_ERROR,
                payload={"stage": "synthesis", "error": str(e)},
                error=str(e),
            )
            logger.error(f"Voice synthesis failed: {e}")
            raise

    async def _publish_event(
        self,
        event_type: EventType,
        payload: dict,
        error: Optional[str] = None,
    ) -> None:
        """Publish a voice lifecycle event to EventBus if connected."""
        if self.event_bus is not None:
            try:
                event = AgentEvent(
                    event_type=event_type,
                    source="core.voice",
                    payload=payload,
                    error=error,
                )
                await self.event_bus.publish(event)
            except Exception as e:
                logger.warning(f"Failed to publish voice event {event_type.value}: {e}")
