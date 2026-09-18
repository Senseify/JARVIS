"""Tests for AutonomousPlanner and RecoveryEngine."""

import pytest
from core.models.ai import ToolCallDefinition
from core.models.planning import FailureClassification, PlanStatus, PlanStep, StepStatus
from core.planning.planner import AutonomousPlanner
from core.planning.recovery import RecoveryEngine
from core.security.policy import SecurityPolicyEngine


def test_planner_creates_validated_plan():
    planner = AutonomousPlanner()
    tool_calls = [
        ToolCallDefinition(tool="app.launch", arguments={"app": "notepad"}),
        ToolCallDefinition(tool="keyboard.type", arguments={"text": "hello"}),
    ]

    plan = planner.create_plan_from_tool_calls("Launch notepad and type", tool_calls)

    assert plan.status == PlanStatus.PENDING
    assert len(plan.steps) == 2

    step1 = plan.steps[0]
    step2 = plan.steps[1]

    assert step1.tool == "app.launch"
    assert step1.verification_required is True
    assert step2.tool == "keyboard.type"
    assert step2.depends_on == [step1.step_id]

    retrieved = planner.get_plan(plan.plan_id)
    assert retrieved is not None
    assert retrieved.plan_id == plan.plan_id


def test_planner_rejects_disallowed_actions():
    planner = AutonomousPlanner(security_policy=SecurityPolicyEngine())
    tool_calls = [
        ToolCallDefinition(tool="shell.execute", arguments={"cmd": "whoami"}),
    ]

    with pytest.raises(PermissionError) as exc_info:
        planner.create_plan_from_tool_calls("Run shell", tool_calls)

    assert "rejected by security policy" in str(exc_info.value)


def test_recovery_engine_failure_classification():
    recovery = RecoveryEngine()

    assert recovery.classify_failure("Window not found for title Notepad") == FailureClassification.WINDOW_NOT_FOUND
    assert recovery.classify_failure("Element not found: Button Play") == FailureClassification.ELEMENT_NOT_FOUND
    assert recovery.classify_failure("Verification failed: OCR text mismatch") == FailureClassification.VERIFICATION_FAILED
    assert recovery.classify_failure("Action timed out after 30s") == FailureClassification.TIMEOUT
    assert recovery.classify_failure("Blocked by security policy") == FailureClassification.POLICY_BLOCKED


@pytest.mark.asyncio
async def test_recovery_engine_retry_limit():
    recovery = RecoveryEngine()
    step = PlanStep(
        name="Click target",
        tool="mouse.click",
        arguments={},
        max_retries=2,
    )

    # First attempt -> succeeds (count: 1)
    can_retry1 = await recovery.attempt_recovery(step, "plan_1", FailureClassification.ELEMENT_NOT_FOUND)
    assert can_retry1 is True
    assert step.retry_count == 1
    assert step.status == StepStatus.RECOVERING

    # Second attempt -> succeeds (count: 2)
    can_retry2 = await recovery.attempt_recovery(step, "plan_1", FailureClassification.ELEMENT_NOT_FOUND)
    assert can_retry2 is True
    assert step.retry_count == 2

    # Third attempt -> exceeds max_retries (2) -> returns False
    can_retry3 = await recovery.attempt_recovery(step, "plan_1", FailureClassification.ELEMENT_NOT_FOUND)
    assert can_retry3 is False
    assert step.status == StepStatus.FAILED
