"""Tests for Voice REST API endpoints."""

import base64
import pytest
from starlette.testclient import TestClient

from core.main import RuntimeContainer, create_app
from core.voice.audio import create_wav_pcm


@pytest.fixture
def api_client(tmp_path):
    db_file = str(tmp_path / "voice_api.db")
    container = RuntimeContainer(db_path=db_file)
    app = create_app(container=container)
    with TestClient(app) as client:
        yield client, container


def test_voice_status_api(api_client):
    """Verify GET /voice/status returns active status."""
    client, _ = api_client
    resp = client.get("/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["current_stt_provider"] == "deterministic"
    assert data["current_tts_provider"] == "deterministic"


def test_voice_transcribe_api(api_client):
    """Verify POST /voice/transcribe processes base64 audio and returns transcript."""
    client, _ = api_client

    wav = create_wav_pcm(b"\x00\x00" * 3000, sample_rate=16000)
    b64_audio = base64.b64encode(wav).decode("ascii")

    resp = client.post(
        "/voice/transcribe",
        json={
            "audio_base64": b64_audio,
            "format": "wav",
            "sample_rate": 16000,
            "channels": 1,
            "metadata": {"expected_transcript": "Show system status"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Show system status"
    assert data["confidence"] > 0.9


def test_voice_speak_api(api_client):
    """Verify POST /voice/speak synthesizes speech and returns valid audio."""
    client, _ = api_client

    resp = client.post(
        "/voice/speak",
        json={
            "text": "Hello, how may I assist you today?",
            "speed": 1.0,
            "pitch": 1.0,
            "format": "wav",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["audio_bytes_length"] > 0
    assert data["duration_seconds"] > 0
    assert data["format"] == "wav"

    decoded = base64.b64decode(data["audio_base64"])
    assert decoded.startswith(b"RIFF")


def test_voice_api_validation_errors(api_client):
    """Verify error responses for invalid voice requests."""
    client, _ = api_client

    # Empty text in speak request -> 422
    resp_empty_text = client.post("/voice/speak", json={"text": "   "})
    assert resp_empty_text.status_code == 422

    # Malformed base64 in transcribe request -> 400
    resp_invalid_b64 = client.post(
        "/voice/transcribe",
        json={"audio_base64": "!!!not_base64!!!"},
    )
    assert resp_invalid_b64.status_code == 400
