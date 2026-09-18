"""Task models for JARVIS OS."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from core.constants import AgentLoopState, TaskStatus


class Task(BaseModel):
    """Core Task abstraction representing a unit of autonomous execution."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    input: str
    state: AgentLoopState = AgentLoopState.IDLE
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to current UTC time."""
        self.updated_at = datetime.now(timezone.utc)


class TaskCreateRequest(BaseModel):
    """Schema for creating a new task via the API."""

    input: str = Field(..., min_length=1, description="The user or system instruction for the task")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary task metadata")
    execute_immediately: bool = Field(default=True, description="Whether to execute the task immediately upon creation")


class TaskStatusResponse(BaseModel):
    """Lightweight schema for checking task status."""

    id: str
    state: AgentLoopState
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None
