"""Tests for Voice Command Pipeline REST API endpoints."""

import base64
from typing import Any, Dict
import pytest
from starlette.testclient import TestClient

from core.main import RuntimeContainer, create_app
from core.voice.audio import create_wav_pcm


@pytest.fixture
def api_client(tmp_path):
    db_file = str(tmp_path / "voice_cmd_api.db")
    container = RuntimeContainer(db_path=db_file)
    app = create_app(container=container)
    with TestClient(app) as client:
        yield client, container


def test_post_voice_command_audio_api(api_client):
    """Verify POST /voice/command with audio input."""
    client, container = api_client

    # Attach mock dispatcher to container's skill executor
    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        return {
            "success": True,
            "verified": True,
            "action_capability": "app.launch",
            "action_receipt": {"success": True},
        }

    container.skill_executor.command_dispatcher = mock_dispatcher

    wav = create_wav_pcm(b"\x00\x00" * 3000, sample_rate=16000)
    b64_audio = base64.b64encode(wav).decode("ascii")

    resp = client.post(
        "/voice/command",
        json={
            "voice_input": {
                "audio_base64": b64_audio,
                "format": "wav",
                "sample_rate": 16000,
                "channels": 1,
                "metadata": {"expected_transcript": "open calculator"},
            },
            "synthesize_response": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["transcript"] == "open calculator"
    assert data["response_text"] == "Opening Calculator."
    assert data["synthesized_audio"] is not None
    assert data["verification_status"] == "verified"


def test_post_voice_command_text_api(api_client):
    """Verify POST /voice/command/text direct text endpoint."""
    client, container = api_client

    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        return {
            "success": True,
            "verified": True,
            "action_capability": "keyboard.type",
            "action_receipt": {"success": True},
        }

    container.skill_executor.command_dispatcher = mock_dispatcher

    resp = client.post("/voice/command/text?text=type%20welcome%20home")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["transcript"] == "type welcome home"
    assert data["response_text"] == "Done. The text was entered."


def test_post_voice_command_unknown_intent_api(api_client):
    """Verify POST /voice/command/text with unrecognized command returns honest response."""
    client, _ = api_client

    resp = client.post("/voice/command/text?text=do%20something%20completely%20unsupported")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["status"] == "unrecognized"
    assert data["response_text"] == "I didn't understand that command."
