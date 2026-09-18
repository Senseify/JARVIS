"""Structured message and event models for internal agent communication."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

from core.constants import AgentLoopState, EventType, TaskStatus


class AgentEvent(BaseModel):
    """Structured runtime event emitted during task execution and lifecycle changes."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_id: Optional[str] = None
    event_type: EventType
    source: str = "core.runtime"
    state: Optional[AgentLoopState] = None
    status: Optional[TaskStatus] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
