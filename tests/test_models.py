"""Tests for Phase 2 structured models."""

import json
from datetime import datetime, timezone
from core.constants import AgentLoopState, DeviceStatus, DeviceType, EventType, TaskStatus
from core.models.devices import Device, DeviceCreateRequest
from core.models.events import AgentEvent
from core.models.tasks import Task, TaskCreateRequest, TaskStatusResponse


def test_agent_event_serialization():
    """Verify AgentEvent serializes to JSON cleanly with correct ISO timestamps."""
    event = AgentEvent(
        task_id="task-123",
        event_type=EventType.ACTION_COMPLETED,
        state=AgentLoopState.ACT,
        status=TaskStatus.RUNNING,
        payload={"action": "demo", "status": "ok"},
    )
    event_json = event.model_dump_json()
    data = json.loads(event_json)

    assert data["task_id"] == "task-123"
    assert data["event_type"] == "action_completed"
    assert data["state"] == "act"
    assert data["status"] == "running"
    assert data["payload"]["action"] == "demo"
    assert isinstance(data["timestamp"], str)


def test_task_model_lifecycle():
    """Verify Task model updates timestamps and properties."""
    task = Task(input="Verify runtime execution")
    initial_updated = task.updated_at
    assert task.status == TaskStatus.PENDING
    assert task.state == AgentLoopState.IDLE
    assert task.result is None

    task.update_timestamp()
    assert task.updated_at >= initial_updated


def test_device_model():
    """Verify Device model defaults and capabilities."""
    device = Device(name="Test Workstation", device_type=DeviceType.WINDOWS_HOST)
    assert device.name == "Test Workstation"
    assert device.device_type == DeviceType.WINDOWS_HOST
    assert device.status == DeviceStatus.ONLINE
    assert device.capabilities == []
