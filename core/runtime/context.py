"""Execution context definition for per-task runtime state."""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from core.models.tasks import Task


class ExecutionContext(BaseModel):
    """Encapsulates runtime state, environment, and history for a single task."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task: Task
    device_id: Optional[str] = None
    permissions: set[str] = Field(default_factory=set)
    available_tools: list[str] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    action_results: list[dict[str, Any]] = Field(default_factory=list)
    verification_results: list[dict[str, Any]] = Field(default_factory=list)
    recovery_attempts: list[dict[str, Any]] = Field(default_factory=list)
    memory_entries: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_observation(self, observation_type: str, data: dict[str, Any]) -> None:
        """Record an environmental or contextual observation."""
        self.observations.append({"type": observation_type, "data": data})

    def add_action_result(self, action: str, success: bool, output: Any) -> None:
        """Record the outcome of a dispatched action."""
        self.action_results.append({"action": action, "success": success, "output": output})

    def add_verification(self, verified: bool, details: str) -> None:
        """Record post-action verification result."""
        self.verification_results.append({"verified": verified, "details": details})

    def add_recovery_attempt(self, strategy: str, recovered: bool, details: str) -> None:
        """Record an applied recovery strategy."""
        self.recovery_attempts.append({"strategy": strategy, "recovered": recovered, "details": details})

    def add_memory(self, key: str, value: Any) -> None:
        """Record contextual information to persist."""
        self.memory_entries.append({"key": key, "value": value})
