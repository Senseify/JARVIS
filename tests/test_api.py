"""Tests for FastAPI HTTP and WebSocket endpoints."""

import asyncio
import json
import pytest
from starlette.testclient import TestClient

from core.main import RuntimeContainer, create_app


@pytest.fixture
def app_and_client(tmp_path):
    db_file = str(tmp_path / "api_test.db")
    container = RuntimeContainer(db_path=db_file)
    app = create_app(container=container)
    with TestClient(app) as client:
        yield app, client, container


def test_health_and_info(app_and_client):
    _, client, _ = app_and_client

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    info = client.get("/info")
    assert info.status_code == 200
    data = info.json()
    assert "agent_loop_states" in data
    assert "demo_verification_tool" in data["registered_tools"]


def test_task_creation_and_retrieval(app_and_client):
    _, client, container = app_and_client

    # Create task without immediate execution
    resp = client.post(
        "/tasks",
        json={"input": "Test task API", "execute_immediately": False, "metadata": {"test": True}},
    )
    assert resp.status_code == 201
    task_data = resp.json()
    task_id = task_data["id"]
    assert task_data["status"] == "pending"

    # Get task by ID
    get_resp = client.get(f"/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == task_id

    # Get task status
    status_resp = client.get(f"/tasks/{task_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "pending"

    # List tasks
    list_resp = client.get("/tasks")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Execute task explicitly
    exec_resp = client.post(f"/tasks/{task_id}/execute")
    assert exec_resp.status_code == 200
    assert exec_resp.json()["status"] == "completed"

    # Fetch events for task
    events_resp = client.get(f"/tasks/{task_id}/events")
    assert events_resp.status_code == 200
    assert len(events_resp.json()) > 0


def test_device_api(app_and_client):
    _, client, _ = app_and_client

    dev_resp = client.post(
        "/devices",
        json={
            "name": "Host PC",
            "device_type": "windows_host",
            "capabilities": ["screen", "keyboard"],
        },
    )
    assert dev_resp.status_code == 201
    dev_data = dev_resp.json()
    assert dev_data["name"] == "Host PC"

    list_resp = client.get("/devices")
    assert list_resp.status_code == 200
    assert any(d["name"] == "Host PC" for d in list_resp.json())


def test_tools_api(app_and_client):
    _, client, _ = app_and_client
    tools_resp = client.get("/tools")
    assert tools_resp.status_code == 200
    tools = tools_resp.json()
    assert any(t["name"] == "demo_verification_tool" for t in tools)


def test_websocket_event_streaming(app_and_client):
    """Verify WebSocket client receives streamed AgentEvents in real time."""
    _, client, container = app_and_client

    with client.websocket_connect("/ws/events") as websocket:
        # Create and execute a task synchronously
        exec_resp = client.post(
            "/tasks",
            json={"input": "Stream events demo", "execute_immediately": False},
        )
        task_id = exec_resp.json()["id"]

        # Run task execution
        client.post(f"/tasks/{task_id}/execute")

        # Receive streamed messages over websocket
        received_events = []
        for _ in range(5):
            message_text = websocket.receive_text()
            event = json.loads(message_text)
            received_events.append(event)

        assert len(received_events) >= 5
        event_types = [e["event_type"] for e in received_events]
        assert "task_state_changed" in event_types or "action_started" in event_types
