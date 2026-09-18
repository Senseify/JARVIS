"""Skills subsystem for JARVIS OS."""

from core.skills.builtin import (
    create_click_and_verify_skill,
    create_launch_and_verify_skill,
    create_type_and_verify_skill,
    get_builtin_skills,
)
from core.skills.executor import SkillExecutor, interpolate_template
from core.skills.registry import SkillRegistry

__all__ = [
    "SkillRegistry",
    "SkillExecutor",
    "interpolate_template",
    "create_launch_and_verify_skill",
    "create_type_and_verify_skill",
    "create_click_and_verify_skill",
    "get_builtin_skills",
]
