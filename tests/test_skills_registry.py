"""Tests for JARVIS OS SkillRegistry operations, deduplication, and capability checking."""

import pytest

from core.models.skills import SkillDefinition, SkillStep
from core.skills.registry import SkillRegistry


def _sample_skill(skill_id: str = "sample_skill") -> SkillDefinition:
    return SkillDefinition(
        id=skill_id,
        name="Sample Skill",
        description="A sample test skill",
        required_capabilities=["app.launch", "window.list"],
        steps=[
            SkillStep(
                step_id="step_1",
                capability="app.launch",
                parameters_template={"app_name": "notepad"},
            )
        ],
    )


def test_registry_registration_and_retrieval():
    """Verify registration, lookup, has_skill, and listing in SkillRegistry."""
    registry = SkillRegistry()
    skill = _sample_skill("calc_launcher")

    assert not registry.has_skill("calc_launcher")
    registry.register_skill(skill)

    assert registry.has_skill("calc_launcher")
    assert registry.has_skill("CALC_LAUNCHER")  # Case-insensitive

    fetched = registry.get_skill("calc_launcher")
    assert fetched is not None
    assert fetched.id == "calc_launcher"
    assert len(registry.list_skills()) == 1


def test_registry_rejects_duplicate_registration():
    """Verify duplicate skill IDs are rejected with ValueError."""
    registry = SkillRegistry()
    skill1 = _sample_skill("duplicate_id")
    skill2 = _sample_skill("DUPLICATE_ID")

    registry.register_skill(skill1)
    with pytest.raises(ValueError, match="already registered"):
        registry.register_skill(skill2)


def test_registry_unregistration():
    """Verify unregistering skills."""
    registry = SkillRegistry()
    skill = _sample_skill("temp_skill")
    registry.register_skill(skill)

    assert registry.unregister_skill("temp_skill")
    assert not registry.has_skill("temp_skill")
    assert not registry.unregister_skill("temp_skill")


def test_registry_capability_checking():
    """Verify checking skill required capabilities against available lists."""
    registry = SkillRegistry()
    skill = _sample_skill("multi_cap_skill")
    registry.register_skill(skill)

    # Missing window.list
    satisfied, missing = registry.check_capabilities("multi_cap_skill", ["app.launch"])
    assert not satisfied
    assert missing == ["window.list"]

    # All available
    satisfied, missing = registry.check_capabilities("multi_cap_skill", ["app.launch", "window.list", "extra.cap"])
    assert satisfied
    assert missing == []

    # Non-existent skill raises KeyError
    with pytest.raises(KeyError):
        registry.check_capabilities("non_existent", ["app.launch"])
