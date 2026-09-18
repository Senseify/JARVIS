"""Tests for VoiceCommandService end-to-end execution, skills routing, verification, and memory."""

import base64
from typing import Any, Dict
import pytest

from core.constants import EventType
from core.events.bus import EventBus
from core.memory.service import MemoryService
from core.memory.store import MemoryStore
from core.models.events import AgentEvent
from core.models.memory import MemoryType
from core.models.voice import VoiceInput
from core.models.voice_command import VoiceCommandRequest
from core.persistence.database import Database
from core.skills.builtin import get_builtin_skills
from core.skills.executor import SkillExecutor
from core.skills.registry import SkillRegistry
from core.tasks.manager import TaskManager
from core.voice.audio import create_wav_pcm
from core.voice.command_service import VoiceCommandService
from core.voice.service import VoiceService


@pytest.fixture
async def voice_environment(tmp_path):
    db_file = str(tmp_path / "voice_cmd_test.db")
    db = Database(db_path=db_file)
    await db.connect()

    event_bus = EventBus(database=db)
    task_manager = TaskManager(database=db, event_bus=event_bus)
    memory_store = MemoryStore(database=db)
    memory_service = MemoryService(store=memory_store)

    skill_registry = SkillRegistry()
    for skill in get_builtin_skills():
        skill_registry.register_skill(skill)

    voice_service = VoiceService(event_bus=event_bus)

    yield {
        "db": db,
        "event_bus": event_bus,
        "task_manager": task_manager,
        "memory_service": memory_service,
        "skill_registry": skill_registry,
        "voice_service": voice_service,
    }

    await db.close()


@pytest.mark.asyncio
async def test_voice_command_successful_app_launch(voice_environment):
    """Verify full pipeline: Audio -> STT -> Parser -> launch_and_verify -> Verification -> Memory -> TTS."""
    env = voice_environment

    dispatched = []

    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        dispatched.append((capability, params))
        return {
            "success": True,
            "verified": True,
            "action_capability": "app.launch",
            "action_receipt": {"success": True},
        }

    executor = SkillExecutor(
        registry=env["skill_registry"],
        memory_service=env["memory_service"],
        command_dispatcher=mock_dispatcher,
    )

    cmd_service = VoiceCommandService(
        voice_service=env["voice_service"],
        skill_executor=executor,
        task_manager=env["task_manager"],
        memory_service=env["memory_service"],
        event_bus=env["event_bus"],
    )

    # Track events
    events = []

    async def listener(evt: AgentEvent):
        events.append(evt)

    env["event_bus"].subscribe(listener)

    # Create audio input requesting "open notepad" via metadata override
    wav = create_wav_pcm(b"\x00\x00" * 3000, sample_rate=16000)
    voice_input = VoiceInput(
        audio_base64=base64.b64encode(wav).decode("ascii"),
        metadata={"expected_transcript": "open notepad"},
    )

    req = VoiceCommandRequest(voice_input=voice_input)
    result = await cmd_service.execute_voice_command(req)

    # Assertions on final result
    assert result.success is True
    assert result.status == "completed"
    assert result.transcript == "open notepad"
    assert result.response_text == "Opening Notepad."
    assert result.synthesized_audio is not None
    assert result.verification_status == "verified"
    assert result.task_id is not None

    # Assert skill was executed
    assert len(dispatched) == 1
    assert dispatched[0][0] == "action.verify"
    assert dispatched[0][1]["action_parameters"]["app_name"] == "notepad"

    # Verify TaskManager completed task
    task = await env["task_manager"].get_task(result.task_id)
    assert task is not None
    assert task.status.value == "completed"

    # Verify MemoryService stored outcome (only 1 voice command outcome)
    mems = await env["memory_service"].search_memory(query="Voice command")
    assert len(mems) >= 1
    assert any("Opening Notepad" in m.entry.content for m in mems)

    # Verify EventBus published lifecycle events
    event_types = [e.event_type for e in events]
    assert EventType.VOICE_COMMAND_RECEIVED in event_types
    assert EventType.VOICE_COMMAND_UNDERSTOOD in event_types
    assert EventType.VOICE_COMMAND_EXECUTION_STARTED in event_types
    assert EventType.VOICE_COMMAND_EXECUTION_COMPLETED in event_types
    assert EventType.VOICE_COMMAND_RESPONSE_READY in event_types


@pytest.mark.asyncio
async def test_voice_command_verification_failure_reporting(voice_environment):
    """Verify that if verification fails, honest error is reported and spoken."""
    env = voice_environment

    async def mock_failing_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        return {
            "success": True,
            "verified": False,
            "failure_reason": "Window title Notepad not found.",
        }

    executor = SkillExecutor(
        registry=env["skill_registry"],
        memory_service=env["memory_service"],
        command_dispatcher=mock_failing_dispatcher,
    )

    cmd_service = VoiceCommandService(
        voice_service=env["voice_service"],
        skill_executor=executor,
        task_manager=env["task_manager"],
        memory_service=env["memory_service"],
        event_bus=env["event_bus"],
    )

    req = VoiceCommandRequest(text_override="open notepad")
    result = await cmd_service.execute_voice_command(req)

    assert result.success is False
    assert result.status == "failed"
    assert result.verification_status == "failed"
    assert "could not be verified" in result.response_text
    assert result.synthesized_audio is not None


@pytest.mark.asyncio
async def test_voice_command_unknown_intent_rejection(voice_environment):
    """Verify unrecognized speech does not trigger execution."""
    env = voice_environment

    cmd_service = VoiceCommandService(
        voice_service=env["voice_service"],
        task_manager=env["task_manager"],
        memory_service=env["memory_service"],
        event_bus=env["event_bus"],
    )

    req = VoiceCommandRequest(text_override="format hard drive now")
    result = await cmd_service.execute_voice_command(req)

    assert result.success is False
    assert result.status == "unrecognized"
    assert result.response_text == "I didn't understand that command."
    assert result.synthesized_audio is not None
