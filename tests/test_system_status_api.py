"""Tests for GET /system/status and AI REST endpoints."""

import pytest
from starlette.testclient import TestClient
from core.main import RuntimeContainer, create_app


@pytest.fixture
def test_app():
    container = RuntimeContainer(db_path=":memory:")
    app = create_app(container)
    with TestClient(app) as client:
        yield client, container


def test_get_system_status(test_app):
    client, _ = test_app
    resp = client.get("/system/status")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "operational"
    assert "version" in data
    assert data["core"]["running"] is True
    assert data["model_runtime"]["status"] == "ready"
    assert data["voice"]["status"] == "operational"
    assert "security" in data
    assert "allowlisted_apps" in data["security"]


def test_get_security_policy(test_app):
    client, _ = test_app
    resp = client.get("/system/security/policy")
    assert resp.status_code == 200

    data = resp.json()
    assert "notepad" in data["allowlisted_apps"]
    assert len(data["blocked_tools"]) > 0


def test_ai_models_and_selection(test_app):
    client, _ = test_app

    # List
    resp = client.get("/ai/models")
    assert resp.status_code == 200
    models = resp.json()
    assert len(models) >= 2

    # Select valid
    sel_resp = client.post("/ai/models/select?name=deterministic")
    assert sel_resp.status_code == 200
    assert sel_resp.json()["active_provider"] == "deterministic"

    # Select invalid
    err_resp = client.post("/ai/models/select?name=fake_unknown_model")
    assert err_resp.status_code == 400


def test_ai_chat_endpoint(test_app):
    client, _ = test_app

    # Conversational chat
    chat_payload = {"message": "Who are you?", "session_id": "test_api_sess"}
    resp = client.post("/ai/chat", json=chat_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["requires_action"] is False
    assert "JARVIS" in data["message"]


def test_ai_plan_creation_endpoint(test_app):
    client, _ = test_app

    payload = {
        "goal": "Launch notepad",
        "tools": [{"tool": "app.launch", "arguments": {"app": "notepad"}}],
    }
    resp = client.post("/ai/plan?goal=Launch%20notepad", json=payload["tools"])
    assert resp.status_code == 200
    plan_data = resp.json()
    assert len(plan_data["steps"]) == 1
    assert plan_data["steps"][0]["tool"] == "app.launch"
