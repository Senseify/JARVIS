"""Tests for AgentRuntime and the autonomous lifecycle loop."""

import pytest
from core.constants import AgentLoopState, EventType, TaskStatus
from core.events.bus import EventBus
from core.models.events import AgentEvent
from core.persistence.database import Database
from core.runtime.agent_runtime import AgentRuntime
from core.tasks.manager import TaskManager
from core.tools.demo import DemoVerificationTool
from core.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_deterministic_demo_task_lifecycle(tmp_path):
    """Verify a task executes through all lifecycle stages and completes successfully."""
    db = Database(db_path=str(tmp_path / "runtime.db"))
    await db.connect()
    bus = EventBus(database=db)
    tools = ToolRegistry()
    tools.register_tool(DemoVerificationTool())
    tasks = TaskManager(database=db, event_bus=bus)

    runtime = AgentRuntime(task_manager=tasks, tool_registry=tools, event_bus=bus)

    # Track emitted events
    emitted_events: list[AgentEvent] = []

    async def event_collector(event: AgentEvent):
        emitted_events.append(event)

    bus.subscribe(event_collector)

    # Create and run demo task
    task = await tasks.create_task("JARVIS runtime verification")
    completed_task = await runtime.execute_task(task.id)

    assert completed_task.status == TaskStatus.COMPLETED
    assert completed_task.state == AgentLoopState.IDLE
    assert completed_task.result is not None
    assert completed_task.result["lifecycle_completed"] is True
    assert completed_task.result["observations_count"] > 0
    assert len(completed_task.result["actions_executed"]) > 0
    assert len(completed_task.result["verifications"]) > 0
    assert len(completed_task.result["memories_persisted"]) > 0

    # Verify event types were emitted
    event_types = [e.event_type for e in emitted_events]
    assert EventType.TASK_CREATED in event_types
    assert EventType.TASK_STATE_CHANGED in event_types
    assert EventType.ACTION_STARTED in event_types
    assert EventType.ACTION_COMPLETED in event_types
    assert EventType.VERIFICATION_STARTED in event_types
    assert EventType.VERIFICATION_COMPLETED in event_types
    assert EventType.MEMORY_STORED in event_types
    assert EventType.TASK_COMPLETED in event_types

    # Verify events persisted in database
    db_events = await db.get_events_for_task(task.id)
    assert len(db_events) >= 5

    await db.close()


@pytest.mark.asyncio
async def test_verification_failure_with_successful_recovery(tmp_path):
    """Verify runtime enters RECOVER on verification failure and completes if recovered."""
    db = Database(db_path=str(tmp_path / "recovery.db"))
    await db.connect()
    bus = EventBus(database=db)
    tools = ToolRegistry()
    tools.register_tool(DemoVerificationTool())
    tasks = TaskManager(database=db, event_bus=bus)
    runtime = AgentRuntime(task_manager=tasks, tool_registry=tools, event_bus=bus)

    task = await tasks.create_task("Task requiring recovery")
    completed = await runtime.execute_task(
        task.id,
        simulate_verification_failure=True,
        allow_recovery=True,
    )

    assert completed.status == TaskStatus.COMPLETED
    assert len(completed.result["recovery_attempts"]) == 1
    assert completed.result["recovery_attempts"][0]["recovered"] is True

    await db.close()


@pytest.mark.asyncio
async def test_verification_failure_with_exhausted_recovery(tmp_path):
    """Verify runtime marks task FAILED if verification fails and recovery is exhausted."""
    db = Database(db_path=str(tmp_path / "unrecoverable.db"))
    await db.connect()
    bus = EventBus(database=db)
    tools = ToolRegistry()
    tasks = TaskManager(database=db, event_bus=bus)
    runtime = AgentRuntime(task_manager=tasks, tool_registry=tools, event_bus=bus)

    task = await tasks.create_task("Unrecoverable failure task")
    failed = await runtime.execute_task(
        task.id,
        simulate_verification_failure=True,
        allow_recovery=False,
    )

    assert failed.status == TaskStatus.FAILED
    assert "recovery strategy was exhausted" in (failed.error or "")

    await db.close()


@pytest.mark.asyncio
async def test_runtime_remember_stage_persists_memories(tmp_path):
    """Verify runtime REMEMBER stage stores persistent memories in MemoryService."""
    from core.memory.service import MemoryService
    from core.memory.store import MemoryStore

    db = Database(db_path=str(tmp_path / "runtime_memories.db"))
    await db.connect()
    bus = EventBus(database=db)
    tools = ToolRegistry()
    tools.register_tool(DemoVerificationTool())
    tasks = TaskManager(database=db, event_bus=bus)
    store = MemoryStore(database=db)
    memory_service = MemoryService(store=store)

    runtime = AgentRuntime(
        task_manager=tasks,
        tool_registry=tools,
        event_bus=bus,
        memory_service=memory_service,
    )

    # 1. Execute successful task
    task = await tasks.create_task("Autonomous memory integration task")
    completed = await runtime.execute_task(task.id)
    assert completed.status == TaskStatus.COMPLETED

    # Verify memories were persisted for this task
    task_memories = await memory_service.search_memory(task_id=task.id)
    assert len(task_memories) == 2
    types = [m.entry.memory_type.value for m in task_memories]
    assert "task_context" in types
    assert "outcome" in types

    # 2. Execute failed task
    failed_task = await tasks.create_task("Failed task memory test")
    failed = await runtime.execute_task(
        failed_task.id,
        simulate_verification_failure=True,
        allow_recovery=False,
    )
    assert failed.status == TaskStatus.FAILED

    failed_memories = await memory_service.search_memory(task_id=failed_task.id)
    assert len(failed_memories) == 1
    assert failed_memories[0].entry.memory_type.value == "outcome"
    assert "failed" in failed_memories[0].entry.content

    await db.close()
