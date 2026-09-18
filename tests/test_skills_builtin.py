"""Tests for JARVIS OS built-in skills definitions and execution."""

import pytest
from typing import Any, Dict

from core.models.skills import SkillExecuteRequest
from core.skills.builtin import (
    create_click_and_verify_skill,
    create_launch_and_verify_skill,
    create_type_and_verify_skill,
    get_builtin_skills,
)
from core.skills.executor import SkillExecutor
from core.skills.registry import SkillRegistry


def test_builtin_skills_definitions():
    """Verify built-in skills schemas and registration."""
    skills = get_builtin_skills()
    assert len(skills) == 3

    ids = {s.id for s in skills}
    assert ids == {"launch_and_verify", "type_and_verify", "click_and_verify"}

    launch_skill = create_launch_and_verify_skill()
    assert "app.launch" in launch_skill.required_capabilities
    assert "action.verify" in launch_skill.required_capabilities
    assert "app_name" in launch_skill.input_schema
    assert launch_skill.steps[0].capability == "action.verify"

    type_skill = create_type_and_verify_skill()
    assert "keyboard.type" in type_skill.required_capabilities
    assert "text" in type_skill.input_schema

    click_skill = create_click_and_verify_skill()
    assert "mouse.click" in click_skill.required_capabilities


@pytest.mark.asyncio
async def test_execute_launch_and_verify():
    """Verify launch_and_verify skill execution and parameter binding."""
    registry = SkillRegistry()
    for skill in get_builtin_skills():
        registry.register_skill(skill)

    recorded_params = []

    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        recorded_params.append((capability, params))
        return {
            "success": True,
            "verified": True,
            "action_capability": "app.launch",
            "action_receipt": {"success": True},
        }

    executor = SkillExecutor(registry=registry, command_dispatcher=mock_dispatcher)
    req = SkillExecuteRequest(
        inputs={"app_name": "notepad", "window_title": "Untitled - Notepad"},
    )
    result = await executor.execute("launch_and_verify", req)

    assert result.success
    assert result.status == "completed"
    assert len(recorded_params) == 1
    cap, params = recorded_params[0]
    assert cap == "action.verify"
    assert params["action_capability"] == "app.launch"
    assert params["action_parameters"]["app_name"] == "notepad"
    assert params["expected_value"] == "Untitled - Notepad"


@pytest.mark.asyncio
async def test_execute_type_and_verify():
    """Verify type_and_verify skill execution."""
    registry = SkillRegistry()
    for skill in get_builtin_skills():
        registry.register_skill(skill)

    recorded_params = []

    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        recorded_params.append((capability, params))
        return {
            "success": True,
            "verified": True,
            "action_capability": "keyboard.type",
        }

    executor = SkillExecutor(registry=registry, command_dispatcher=mock_dispatcher)
    req = SkillExecuteRequest(
        inputs={
            "text": "Hello World",
            "expected_condition": "text_present",
            "expected_value": "Hello World",
        }
    )
    result = await executor.execute("type_and_verify", req)

    assert result.success
    assert result.status == "completed"
    cap, params = recorded_params[0]
    assert cap == "action.verify"
    assert params["action_capability"] == "keyboard.type"
    assert params["action_parameters"]["text"] == "Hello World"
    assert params["expected_condition"] == "text_present"
    assert params["expected_value"] == "Hello World"


@pytest.mark.asyncio
async def test_execute_click_and_verify():
    """Verify click_and_verify skill execution with coordinates."""
    registry = SkillRegistry()
    for skill in get_builtin_skills():
        registry.register_skill(skill)

    recorded_params = []

    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        recorded_params.append((capability, params))
        return {
            "success": True,
            "verified": True,
            "action_capability": "mouse.click",
        }

    executor = SkillExecutor(registry=registry, command_dispatcher=mock_dispatcher)
    req = SkillExecuteRequest(
        inputs={"x": 500, "y": 300, "button": "left"},
    )
    result = await executor.execute("click_and_verify", req)

    assert result.success
    assert result.status == "completed"
    cap, params = recorded_params[0]
    assert cap == "action.verify"
    assert params["action_capability"] == "mouse.click"
    assert params["action_parameters"]["x"] == 500
    assert params["action_parameters"]["y"] == 300
