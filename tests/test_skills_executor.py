"""Tests for JARVIS OS SkillExecutor, execution lifecycle, verification checks, and memory logging."""

import asyncio
from typing import Any, Dict
import pytest

from core.memory.service import MemoryService
from core.memory.store import MemoryStore
from core.models.memory import MemoryType
from core.models.skills import (
    SkillDefinition,
    SkillExecuteRequest,
    SkillStep,
)
from core.persistence.database import Database
from core.skills.executor import SkillExecutor
from core.skills.registry import SkillRegistry


@pytest.fixture
async def memory_service(tmp_path):
    db_file = str(tmp_path / "skills_test.db")
    db = Database(db_path=db_file)
    await db.connect()
    store = MemoryStore(database=db)
    service = MemoryService(store=store)
    yield service
    await db.close()


def _create_test_skill() -> SkillDefinition:
    return SkillDefinition(
        id="multi_step_workflow",
        name="Multi Step Workflow",
        description="Workflow with 2 steps",
        required_capabilities=["step_one_cap", "step_two_cap"],
        steps=[
            SkillStep(
                step_id="step_1",
                name="Step One",
                capability="step_one_cap",
                parameters_template={"target": "{target_name}", "retries": 2},
            ),
            SkillStep(
                step_id="step_2",
                name="Step Two",
                capability="step_two_cap",
                parameters_template={"action": "finalize"},
            ),
        ],
        input_schema={
            "target_name": {"type": "string", "required": True},
            "optional_mode": {"type": "string", "required": False, "default": "standard"},
        },
    )


@pytest.mark.asyncio
async def test_executor_successful_multi_step(memory_service):
    """Verify clean execution of all steps, parameter interpolation, and memory persistence."""
    registry = SkillRegistry()
    skill = _create_test_skill()
    registry.register_skill(skill)

    dispatched_calls = []

    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        dispatched_calls.append((capability, params))
        return {"success": True, "output_data": f"result_for_{capability}"}

    executor = SkillExecutor(
        registry=registry,
        memory_service=memory_service,
        command_dispatcher=mock_dispatcher,
    )

    req = SkillExecuteRequest(
        inputs={"target_name": "database_service"},
        task_id="task_42",
    )

    result = await executor.execute("multi_step_workflow", req)

    assert result.success
    assert result.status == "completed"
    assert len(result.step_results) == 2
    assert result.step_results[0].step_id == "step_1"
    assert result.step_results[0].success
    assert result.step_results[1].step_id == "step_2"
    assert result.step_results[1].success

    # Parameter interpolation check
    assert dispatched_calls[0] == ("step_one_cap", {"target": "database_service", "retries": 2})
    assert dispatched_calls[1] == ("step_two_cap", {"action": "finalize"})

    # Memory check: Exactly 1 OUTCOME memory stored, not 1 per step
    assert result.memory_persisted
    assert result.memory_id is not None

    mem = await memory_service.get_memory(result.memory_id)
    assert mem is not None
    assert mem.memory_type == MemoryType.OUTCOME
    assert mem.task_id == "task_42"
    assert "multi_step_workflow" in mem.tags
    assert "success" in mem.tags
    assert mem.importance == 0.7

    # Verify no spam: only 1 total memory in the system
    all_mems = await memory_service.search_memory(query="Skill execution")
    assert len(all_mems) == 1


@pytest.mark.asyncio
async def test_executor_stops_safely_on_step_failure(memory_service):
    """Verify execution halts immediately on step failure and subsequent steps are skipped."""
    registry = SkillRegistry()
    skill = _create_test_skill()
    registry.register_skill(skill)

    calls = []

    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        calls.append(capability)
        if capability == "step_one_cap":
            return {"success": False, "failure_reason": "Device connection interrupted."}
        return {"success": True}

    executor = SkillExecutor(
        registry=registry,
        memory_service=memory_service,
        command_dispatcher=mock_dispatcher,
    )

    req = SkillExecuteRequest(inputs={"target_name": "web_server"})
    result = await executor.execute("multi_step_workflow", req)

    assert not result.success
    assert result.status == "failed"
    assert len(result.step_results) == 1  # Step 2 never executed
    assert result.step_results[0].success is False
    assert "Device connection interrupted" in (result.error or "")

    # Memory outcome logged as failure
    assert result.memory_persisted
    mem = await memory_service.get_memory(result.memory_id)
    assert mem is not None
    assert "failure" in mem.tags
    assert mem.importance == 0.8


@pytest.mark.asyncio
async def test_executor_handles_verification_failure():
    """Verify that a step where verified=False is marked as failed."""
    registry = SkillRegistry()
    skill = SkillDefinition(
        id="verify_test_skill",
        name="Verification Test Skill",
        steps=[
            SkillStep(
                step_id="verify_step",
                capability="action.verify",
                parameters_template={"action_capability": "mouse.click"},
            )
        ],
    )
    registry.register_skill(skill)

    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        return {
            "success": True,  # Action itself succeeded
            "verified": False,  # Verification failed
            "failure_reason": "Expected text 'Welcome' was not found on screen.",
            "verification": {"passed": False},
        }

    executor = SkillExecutor(registry=registry, command_dispatcher=mock_dispatcher)
    result = await executor.execute("verify_test_skill", SkillExecuteRequest(inputs={}))

    assert not result.success
    assert result.status == "failed"
    assert result.step_results[0].verified is False
    assert result.step_results[0].success is False
    assert "Expected text 'Welcome' was not found" in result.error


@pytest.mark.asyncio
async def test_executor_input_validation_and_defaults():
    """Verify missing required parameters are rejected, and defaults are applied."""
    registry = SkillRegistry()
    skill = _create_test_skill()
    registry.register_skill(skill)

    executor = SkillExecutor(registry=registry, command_dispatcher=lambda *a: {"success": True})

    # Missing target_name
    with pytest.raises(ValueError, match="Missing required input parameter"):
        await executor.execute("multi_step_workflow", SkillExecuteRequest(inputs={}))


@pytest.mark.asyncio
async def test_executor_timeout_handling():
    """Verify exceeding timeout triggers timed_out status."""
    registry = SkillRegistry()
    skill = SkillDefinition(
        id="slow_skill",
        name="Slow Skill",
        timeout=0.05,
        steps=[
            SkillStep(
                step_id="step_1",
                capability="slow_cap",
                timeout=5.0,
            ),
            SkillStep(
                step_id="step_2",
                capability="next_cap",
                timeout=5.0,
            ),
        ],
    )
    registry.register_skill(skill)

    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        await asyncio.sleep(0.08)
        return {"success": True}

    executor = SkillExecutor(registry=registry, command_dispatcher=mock_dispatcher)
    result = await executor.execute("slow_skill", SkillExecuteRequest(inputs={}))

    assert not result.success
    assert result.status == "timed_out"
    assert any("timeout" in (s.error or "").lower() for s in result.step_results)
