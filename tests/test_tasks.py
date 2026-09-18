"""Tests for TaskManager and state transition validation."""

import pytest
from core.constants import AgentLoopState, EventType, TaskStatus
from core.events.bus import EventBus
from core.persistence.database import Database
from core.tasks.manager import InvalidStateTransitionError, TaskManager


@pytest.mark.asyncio
async def test_task_creation_and_retrieval(tmp_path):
    """Verify task creation sets default fields and persists properly."""
    db = Database(db_path=str(tmp_path / "tasks.db"))
    await db.connect()
    bus = EventBus(database=db)
    manager = TaskManager(database=db, event_bus=bus)

    task = await manager.create_task("Open system diagnostics", metadata={"priority": "high"})
    assert task.input == "Open system diagnostics"
    assert task.state == AgentLoopState.IDLE
    assert task.status == TaskStatus.PENDING
    assert task.metadata["priority"] == "high"

    retrieved = await manager.get_task(task.id)
    assert retrieved is not None
    assert retrieved.id == task.id
    await db.close()


@pytest.mark.asyncio
async def test_valid_lifecycle_transitions(tmp_path):
    """Verify valid progression through the agent lifecycle."""
    db = Database(db_path=str(tmp_path / "transitions.db"))
    await db.connect()
    manager = TaskManager(database=db)

    task = await manager.create_task("Lifecycle progression test")

    # IDLE -> OBSERVE
    task = await manager.update_task_state(task.id, AgentLoopState.OBSERVE)
    assert task.state == AgentLoopState.OBSERVE
    assert task.status == TaskStatus.RUNNING

    # OBSERVE -> UNDERSTAND
    task = await manager.update_task_state(task.id, AgentLoopState.UNDERSTAND)
    assert task.state == AgentLoopState.UNDERSTAND

    # UNDERSTAND -> PLAN
    task = await manager.update_task_state(task.id, AgentLoopState.PLAN)
    assert task.state == AgentLoopState.PLAN

    # PLAN -> ACT
    task = await manager.update_task_state(task.id, AgentLoopState.ACT)
    assert task.state == AgentLoopState.ACT

    # ACT -> VERIFY
    task = await manager.update_task_state(task.id, AgentLoopState.VERIFY)
    assert task.state == AgentLoopState.VERIFY

    # VERIFY -> REMEMBER
    task = await manager.update_task_state(task.id, AgentLoopState.REMEMBER)
    assert task.state == AgentLoopState.REMEMBER

    # Complete task
    completed = await manager.complete_task(task.id, {"status": "ok"})
    assert completed.status == TaskStatus.COMPLETED
    assert completed.state == AgentLoopState.IDLE
    assert completed.result == {"status": "ok"}
    await db.close()


@pytest.mark.asyncio
async def test_invalid_lifecycle_transition(tmp_path):
    """Verify illegal state transitions are rejected with InvalidStateTransitionError."""
    db = Database(db_path=str(tmp_path / "invalid_transitions.db"))
    await db.connect()
    manager = TaskManager(database=db)

    task = await manager.create_task("Invalid transition test")
    assert task.state == AgentLoopState.IDLE

    # Attempt illegal transition: IDLE -> ACT (must go through OBSERVE)
    with pytest.raises(InvalidStateTransitionError):
        await manager.update_task_state(task.id, AgentLoopState.ACT)

    # Attempt illegal transition: IDLE -> PLAN
    with pytest.raises(InvalidStateTransitionError):
        await manager.update_task_state(task.id, AgentLoopState.PLAN)

    # Advance to OBSERVE, then attempt OBSERVE -> ACT (must go to UNDERSTAND)
    await manager.update_task_state(task.id, AgentLoopState.OBSERVE)
    with pytest.raises(InvalidStateTransitionError):
        await manager.update_task_state(task.id, AgentLoopState.ACT)

    await db.close()


@pytest.mark.asyncio
async def test_task_failure_recording(tmp_path):
    """Verify failing a task records error message and sets FAILED status."""
    db = Database(db_path=str(tmp_path / "failures.db"))
    await db.connect()
    manager = TaskManager(database=db)

    task = await manager.create_task("Failure test")
    failed = await manager.fail_task(task.id, "Unrecoverable hardware communication error")

    assert failed.status == TaskStatus.FAILED
    assert failed.error == "Unrecoverable hardware communication error"

    fetched = await manager.get_task(task.id)
    assert fetched.status == TaskStatus.FAILED
    assert fetched.error == "Unrecoverable hardware communication error"
    await db.close()
