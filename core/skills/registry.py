"""SkillRegistry maintaining registered SkillDefinitions and capability validation."""

import logging
from typing import Dict, List, Optional, Tuple

from core.models.skills import SkillDefinition

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registry maintaining available skills, preventing duplicates, and verifying capabilities."""

    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}

    def register_skill(self, skill: SkillDefinition) -> None:
        """Register a new SkillDefinition. Rejects duplicate IDs."""
        skill_id = skill.id.strip().lower()
        if skill_id in self._skills:
            raise ValueError(f"Skill with ID '{skill_id}' is already registered.")
        self._skills[skill_id] = skill
        logger.info(f"Registered skill: {skill_id} ({skill.name}) v{skill.version}")

    def unregister_skill(self, skill_id: str) -> bool:
        """Unregister a skill by ID."""
        key = skill_id.strip().lower()
        if key in self._skills:
            del self._skills[key]
            logger.info(f"Unregistered skill: {key}")
            return True
        return False

    def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        """Retrieve a registered skill by ID."""
        return self._skills.get(skill_id.strip().lower())

    def has_skill(self, skill_id: str) -> bool:
        """Check if a skill is registered."""
        return skill_id.strip().lower() in self._skills

    def list_skills(self) -> List[SkillDefinition]:
        """List all currently registered skill definitions."""
        return list(self._skills.values())

    def check_capabilities(
        self,
        skill_id: str,
        available_capabilities: List[str],
    ) -> Tuple[bool, List[str]]:
        """Verify whether all capabilities required by a skill are available.

        Returns:
            Tuple of (is_satisfied: bool, missing_capabilities: List[str]).
        """
        skill = self.get_skill(skill_id)
        if not skill:
            raise KeyError(f"Skill '{skill_id}' is not registered.")

        avail_set = set(available_capabilities)
        missing = [cap for cap in skill.required_capabilities if cap not in avail_set]
        return (len(missing) == 0, missing)
