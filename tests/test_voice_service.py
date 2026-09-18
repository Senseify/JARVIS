"""Tests for VoiceService orchestration and EventBus lifecycle integration."""

import base64
import pytest

from core.constants import EventType
from core.events.bus import EventBus
from core.models.events import AgentEvent
from core.models.voice import SpeechSynthesisRequest, VoiceInput
from core.persistence.database import Database
from core.voice.audio import create_wav_pcm
from core.voice.service import VoiceService
from core.voice.stt import DeterministicSTTProvider
from core.voice.tts import DeterministicTTSProvider


@pytest.fixture
async def event_bus(tmp_path):
    db_file = str(tmp_path / "voice_events.db")
    db = Database(db_path=db_file)
    await db.connect()
    bus = EventBus(database=db)
    yield bus
    await db.close()


@pytest.mark.asyncio
async def test_voice_service_transcribe_lifecycle(event_bus):
    """Verify transcription lifecycle and event emissions."""
    events = []

    async def listener(evt: AgentEvent):
        events.append(evt)

    event_bus.subscribe(listener)

    service = VoiceService(event_bus=event_bus)

    wav = create_wav_pcm(b"\x00\x00" * 4000, sample_rate=16000)
    b64_audio = base64.b64encode(wav).decode("ascii")

    voice_input = VoiceInput(
        audio_base64=b64_audio,
        metadata={"expected_transcript": "Run system diagnostic"},
    )

    result = await service.transcribe(voice_input)
    assert result.text == "Run system diagnostic"

    # Verify events
    event_types = [e.event_type for e in events]
    assert EventType.VOICE_INPUT_RECEIVED in event_types
    assert EventType.VOICE_TRANSCRIPTION_COMPLETED in event_types

    # Check status
    status = await service.get_status()
    assert status.status == "ready"
    assert status.last_transcription == "Run system diagnostic"


@pytest.mark.asyncio
async def test_voice_service_speak_lifecycle(event_bus):
    """Verify synthesis lifecycle and event emissions."""
    events = []

    async def listener(evt: AgentEvent):
        events.append(evt)

    event_bus.subscribe(listener)

    service = VoiceService(event_bus=event_bus)

    req = SpeechSynthesisRequest(text="Hello commander")
    result = await service.speak(req)

    assert result.audio_bytes_length > 0
    assert result.duration_seconds > 0

    # Verify events
    event_types = [e.event_type for e in events]
    assert EventType.VOICE_SYNTHESIS_STARTED in event_types
    assert EventType.VOICE_SYNTHESIS_COMPLETED in event_types

    status = await service.get_status()
    assert status.status == "ready"
    assert status.last_synthesized_text == "Hello commander"


@pytest.mark.asyncio
async def test_voice_service_error_handling(event_bus):
    """Verify error isolation and VOICE_ERROR event publication."""
    events = []

    async def listener(evt: AgentEvent):
        events.append(evt)

    event_bus.subscribe(listener)

    failing_stt = DeterministicSTTProvider(simulate_failure=True)
    service = VoiceService(stt_provider=failing_stt, event_bus=event_bus)

    wav = create_wav_pcm(b"\x00\x00" * 1000, sample_rate=16000)
    voice_input = VoiceInput(audio_base64=base64.b64encode(wav).decode("ascii"))

    with pytest.raises(RuntimeError):
        await service.transcribe(voice_input)

    event_types = [e.event_type for e in events]
    assert EventType.VOICE_ERROR in event_types

    status = await service.get_status()
    assert status.status in ("degraded", "error")
