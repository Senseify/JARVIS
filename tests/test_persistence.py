"""Tests for SQLite persistence layer."""

import pytest
from core.constants import AgentLoopState, DeviceStatus, DeviceType, EventType, TaskStatus
from core.models.devices import Device
from core.models.events import AgentEvent
from core.models.tasks import Task
from core.persistence.database import Database


@pytest.mark.asyncio
async def test_isolated_task_persistence(tmp_path):
    """Verify tasks are persisted and retrieved from an isolated database."""
    db_file = str(tmp_path / "test_isolated.db")
    db = Database(db_path=db_file)
    await db.connect()

    task = Task(input="Persist this task", state=AgentLoopState.PLAN, status=TaskStatus.RUNNING)
    await db.save_task(task)

    retrieved = await db.get_task(task.id)
    assert retrieved is not None
    assert retrieved.id == task.id
    assert retrieved.input == "Persist this task"
    assert retrieved.state == AgentLoopState.PLAN
    assert retrieved.status == TaskStatus.RUNNING

    # Update and re-fetch
    task.state = AgentLoopState.ACT
    task.result = {"verified": True}
    await db.save_task(task)

    updated = await db.get_task(task.id)
    assert updated.state == AgentLoopState.ACT
    assert updated.result == {"verified": True}

    await db.close()


@pytest.mark.asyncio
async def test_events_persistence(tmp_path):
    """Verify runtime events are recorded and retrieved for a task."""
    db_file = str(tmp_path / "test_events.db")
    db = Database(db_path=db_file)
    await db.connect()

    task_id = "task-event-test-1"
    event1 = AgentEvent(
        task_id=task_id,
        event_type=EventType.ACTION_STARTED,
        state=AgentLoopState.ACT,
        payload={"action": "step1"},
    )
    event2 = AgentEvent(
        task_id=task_id,
        event_type=EventType.ACTION_COMPLETED,
        state=AgentLoopState.ACT,
        payload={"action": "step1", "success": True},
    )

    await db.save_event(event1)
    await db.save_event(event2)

    events = await db.get_events_for_task(task_id)
    assert len(events) == 2
    assert events[0].event_type == EventType.ACTION_STARTED
    assert events[1].event_type == EventType.ACTION_COMPLETED

    await db.close()


@pytest.mark.asyncio
async def test_devices_persistence(tmp_path):
    """Verify device registration, retrieval, listing, and deletion."""
    db_file = str(tmp_path / "test_devices.db")
    db = Database(db_path=db_file)
    await db.connect()

    dev = Device(
        name="Primary Windows Box",
        device_type=DeviceType.WINDOWS_HOST,
        status=DeviceStatus.ONLINE,
        capabilities=["screen_capture", "mouse_keyboard"],
    )
    await db.save_device(dev)

    fetched = await db.get_device(dev.id)
    assert fetched is not None
    assert fetched.name == "Primary Windows Box"
    assert "screen_capture" in fetched.capabilities

    device_list = await db.list_devices()
    assert len(device_list) == 1

    deleted = await db.delete_device(dev.id)
    assert deleted is True
    assert await db.get_device(dev.id) is None

    await db.close()
