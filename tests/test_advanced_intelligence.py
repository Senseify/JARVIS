"""Advanced tests for vision fallback, voice reasoning, knowledge service, and event streaming."""

import pytest
from starlette.testclient import TestClient
from core.ai.vision_reasoning import VisionReasoningAdapter
from core.constants import EventType, OrbState
from core.knowledge.service import KnowledgeService
from core.main import RuntimeContainer, create_app
from core.models.events import AgentEvent
from core.models.voice import VoiceInput
from core.models.voice_command import VoiceCommandRequest


def test_vision_reasoning_fallback_formatting():
    adapter = VisionReasoningAdapter()

    # Screen state with OCR and UI elements, but no vision model
    context_str = adapter.format_screen_context(
        active_window={"title": "Calculator", "app": "calc.exe"},
        ocr_regions=[{"text": "1234"}, {"text": "5678"}],
        ui_elements=[
            {"name": "Clear", "control_type": "button", "bounding_box": {"x": 50, "y": 100}},
            {"name": "Equals", "control_type": "button", "bounding_box": {"x": 150, "y": 200}},
        ],
    )

    assert "Calculator" in context_str
    assert "1234" in context_str
    assert "Clear" in context_str
    assert "Structured OCR & UI Accessibility Fallback" in context_str


def test_knowledge_service_local_vs_web():
    service = KnowledgeService(web_search_enabled=False)

    fact = service.get_local_fact("jarvis_os")
    assert fact is not None
    assert "autonomous" in fact.lower()

    search_res = service.search_local("platforms")
    assert len(search_res) >= 1
    assert search_res[0]["source"] == "local_knowledge"


@pytest.mark.asyncio
async def test_knowledge_service_web_offline_honest_report():
    service = KnowledgeService(web_search_enabled=False)
    web_res = await service.search_web("what is the weather today")

    assert web_res["available"] is False
    assert "disabled in offline mode" in web_res["message"]


@pytest.mark.asyncio
async def test_voice_pipeline_with_reasoning_integration():
    container = RuntimeContainer(db_path=":memory:")
    await container.database.connect()

    # Voice command with reasoning enabled
    req = VoiceCommandRequest(
        text_override="Open Notepad and type test voice",
        use_reasoning=True,
    )
    result = await container.voice_command_service.execute_voice_command(req)

    assert result.success is True
    assert result.verification_status == "verified"
    assert "Successfully completed" in result.response_text or "Launching" in result.response_text
    assert result.synthesized_audio is not None

    await container.database.close()


def test_websocket_event_streaming():
    import json
    container = RuntimeContainer(db_path=":memory:")
    app = create_app(container)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/events") as websocket:
            # Trigger chat request which emits events over event_bus
            client.post(
                "/ai/chat",
                json={"message": "Who are you?", "session_id": "ws_test_sess"},
            )

            # Receive streamed messages over websocket
            received = []
            for _ in range(2):
                msg = websocket.receive_text()
                received.append(json.loads(msg))

            event_types = [e["event_type"] for e in received]
            assert EventType.ORB_STATE_CHANGED in event_types or EventType.REASONING_STARTED in event_types
