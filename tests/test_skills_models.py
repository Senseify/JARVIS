"""Tests for JARVIS OS Skills Engine models and template interpolation."""

import pytest
from pydantic import ValidationError

from core.models.skills import (
    SkillDefinition,
    SkillExecuteRequest,
    SkillExecution,
    SkillResult,
    SkillStep,
    SkillStepResult,
)
from core.skills.executor import interpolate_template


def test_skill_step_validation():
    """Verify valid SkillStep creation and rejection of extra or empty fields."""
    step = SkillStep(
        step_id="step_1",
        name="Launch App",
        capability="app.launch",
        parameters_template={"app_name": "{app_name}"},
        timeout=12.5,
    )
    assert step.step_id == "step_1"
    assert step.capability == "app.launch"
    assert step.timeout == 12.5
    assert not step.continue_on_failure

    # Rejection of empty capability or step_id
    with pytest.raises(ValidationError):
        SkillStep(step_id="", capability="app.launch")

    with pytest.raises(ValidationError):
        SkillStep(step_id="step_1", capability="   ")

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        SkillStep(step_id="step_1", capability="app.launch", unknown_field=123)


def test_skill_definition_validation():
    """Verify SkillDefinition validation, step requirements, and timeout bounds."""
    step = SkillStep(
        step_id="step_1",
        capability="keyboard.type",
        parameters_template={"text": "{text}"},
    )

    skill = SkillDefinition(
        id="type_text_skill",
        name="Type Text Skill",
        description="Types text into focused window",
        version="1.0.0",
        required_capabilities=["keyboard.type"],
        steps=[step],
        timeout=45.0,
        input_schema={"text": {"type": "string", "required": True}},
    )
    assert skill.id == "type_text_skill"
    assert len(skill.steps) == 1
    assert skill.timeout == 45.0

    # Reject empty steps list
    with pytest.raises(ValidationError):
        SkillDefinition(
            id="empty_skill",
            name="Empty Skill",
            steps=[],
        )

    # Reject non-positive timeout
    with pytest.raises(ValidationError):
        SkillDefinition(
            id="invalid_timeout",
            name="Invalid Timeout Skill",
            steps=[step],
            timeout=-5.0,
        )


def test_skill_execution_and_result_models():
    """Verify SkillExecution, SkillStepResult, and SkillResult schemas."""
    step_res = SkillStepResult(
        step_id="step_1",
        capability="mouse.click",
        status="success",
        success=True,
        output={"clicked": True},
        duration_ms=45.2,
        verified=True,
    )
    assert step_res.success
    assert step_res.verified

    execution = SkillExecution(
        skill_id="click_skill",
        inputs={"x": 100, "y": 200},
        step_results=[step_res],
    )
    assert execution.status == "pending"
    assert len(execution.step_results) == 1

    result = SkillResult(
        execution_id=execution.execution_id,
        skill_id="click_skill",
        success=True,
        status="completed",
        step_results=[step_res],
        output={"clicked": True},
        duration_ms=50.0,
        memory_persisted=True,
        memory_id="mem_123",
    )
    assert result.success
    assert result.memory_id == "mem_123"


def test_skill_execute_request():
    """Verify SkillExecuteRequest structure."""
    req = SkillExecuteRequest(
        inputs={"app_name": "notepad"},
        device_id="win_host_1",
        task_id="task_abc",
    )
    assert req.inputs["app_name"] == "notepad"
    assert req.device_id == "win_host_1"
    assert req.task_id == "task_abc"


def test_template_interpolation():
    """Verify recursive and typed template variable replacement."""
    inputs = {
        "app_name": "notepad",
        "x": 1920,
        "y": 1080,
        "active": True,
        "nested": {"key": "value"},
    }

    template = {
        "app": "{app_name}",
        "coords": ["{x}", "{y}"],
        "flag": "{active}",
        "raw_text": "Launch {app_name} now",
        "inner_obj": "{nested}",
    }

    interpolated = interpolate_template(template, inputs)

    # Direct type preservation
    assert interpolated["app"] == "notepad"
    assert interpolated["coords"] == [1920, 1080]
    assert interpolated["flag"] is True
    assert interpolated["inner_obj"] == {"key": "value"}
    # Substring replacement
    assert interpolated["raw_text"] == "Launch notepad now"
