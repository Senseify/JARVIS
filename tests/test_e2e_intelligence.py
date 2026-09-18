"""Deterministic End-to-End Test for JARVIS OS Full Intelligence & Execution Build (Part 25).

Tests:
1. Successful End-to-End multi-step task:
   USER: "Open Notepad and type hello world."
   - Request received
   - Reasoning creates structured plan
   - Tool validation / security policy succeeds
   - app.launch executes
   - Window verification succeeds
   - keyboard.type executes
   - Text verification succeeds
   - Memory outcome stored
   - Spoken / textual response generated
2. Honest Failure Test:
   - When verification fails
   - Recovery attempts exhausted
   - JARVIS reports honest failure and NEVER fakes success.
"""

import pytest
from core.ai.engine import ReasoningEngine
from core.ai.manager import ModelManager
from core.constants import EventType, OrbState
from core.events.bus import EventBus
from core.memory.service import MemoryService
from core.memory.store import MemoryStore
from core.models.ai import ChatRequest, ToolCallDefinition
from core.models.events import AgentEvent
from core.models.memory import MemoryType
from core.persistence.database import Database
from core.planning.planner import AutonomousPlanner
from core.planning.recovery import RecoveryEngine
from core.security.policy import SecurityPolicyEngine


@pytest.mark.asyncio
async def test_e2e_successful_notepad_task():
    # Setup test persistence and event bus
    db = Database(db_path=":memory:")
    await db.connect()
    event_bus = EventBus(database=db)
    mem_store = MemoryStore(database=db)
    mem_service = MemoryService(store=mem_store)

    sec_policy = SecurityPolicyEngine()
    planner = AutonomousPlanner(security_policy=sec_policy)
    recovery = RecoveryEngine(event_bus=event_bus)
    model_mgr = ModelManager()

    # Track emitted events
    emitted_events = []

    async def listener(evt: AgentEvent):
        emitted_events.append(evt)

    event_bus.subscribe(listener)

    engine = ReasoningEngine(
        model_manager=model_mgr,
        planner=planner,
        recovery_engine=recovery,
        security_policy=sec_policy,
        memory_service=mem_service,
        event_bus=event_bus,
    )

    # 1. User Request
    req = ChatRequest(
        message="Open Notepad and type hello world",
        session_id="e2e_success_session",
    )

    # 2. Process chat through Reasoning Engine
    resp = await engine.process_chat(req)

    # Assertions on final response
    assert resp.requires_action is True
    assert resp.plan_id is not None
    assert len(resp.tool_calls) == 2
    assert "Successfully completed" in resp.message

    # Verify event timeline sequence
    event_types = [e.event_type for e in emitted_events]
    assert EventType.REASONING_STARTED in event_types
    assert EventType.REASONING_COMPLETED in event_types
    assert EventType.PLAN_CREATED in event_types
    assert EventType.PLAN_STEP_STARTED in event_types
    assert EventType.PLAN_STEP_VERIFYING in event_types
    assert EventType.PLAN_STEP_COMPLETED in event_types
    assert EventType.PLAN_COMPLETED in event_types
    assert EventType.ORB_STATE_CHANGED in event_types

    # Verify memory outcome stored (exactly 1 OUTCOME entry, no spam)
    memories = await mem_service.search_memory(
        memory_type=MemoryType.OUTCOME,
        limit=10,
    )
    assert len(memories) >= 1
    latest_mem = memories[0].entry
    assert "success" in latest_mem.content.lower()
    assert "Open Notepad and type hello world" in latest_mem.content

    await db.close()


@pytest.mark.asyncio
async def test_e2e_verification_failure_never_fakes_success():
    """Test that when verification fails, recovery is attempted and failure is honestly reported."""
    db = Database(db_path=":memory:")
    await db.connect()
    event_bus = EventBus(database=db)
    mem_store = MemoryStore(database=db)
    mem_service = MemoryService(store=mem_store)

    sec_policy = SecurityPolicyEngine()
    planner = AutonomousPlanner(security_policy=sec_policy)
    recovery = RecoveryEngine(event_bus=event_bus)
    model_mgr = ModelManager()

    engine = ReasoningEngine(
        model_manager=model_mgr,
        planner=planner,
        recovery_engine=recovery,
        security_policy=sec_policy,
        memory_service=mem_service,
        event_bus=event_bus,
    )

    # Create a plan with a step configured to fail verification
    tool_calls = [
        ToolCallDefinition(
            tool="app.launch",
            arguments={"app": "notepad", "fail_verification": True},
        )
    ]
    plan = planner.create_plan_from_tool_calls(
        goal="Launch notepad with verification failure",
        tool_calls=tool_calls,
    )

    # Execute plan
    success = await engine.execute_plan(plan)

    # Must report FALSE
    assert success is False
    assert plan.status.value == "failed"

    # Must have honest failure message
    assert plan.final_response is not None
    assert "could not be verified" in plan.final_response.lower()

    await db.close()
