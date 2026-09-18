from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from core.runtime.context import ExecutionContext


class ToolDefinition(BaseModel):
    """Metadata describing a tool's capability and expected parameters."""

    name: str
    description: str
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    required_permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    """Abstract base class for all JARVIS tools and skills."""

    def __init__(self, definition: ToolDefinition):
        self.definition = definition

    @property
    def name(self) -> str:
        return self.definition.name

    @abstractmethod
    async def execute(self, context: ExecutionContext, **params: Any) -> dict[str, Any]:
        """Execute the tool within the provided task context."""
        pass
