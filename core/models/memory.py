"""Models and schemas for persistent memory entries and operations."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field


class MemoryType(str, Enum):
    """Categorical classification of memory entries."""

    FACT = "fact"
    PREFERENCE = "preference"
    INSTRUCTION = "instruction"
    TASK_CONTEXT = "task_context"
    OBSERVATION = "observation"
    OUTCOME = "outcome"
    SYSTEM = "system"


class MemoryEntry(BaseModel):
    """Structured representation of a persistent memory entry."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique memory ID")
    memory_type: MemoryType = Field(default=MemoryType.FACT, description="Category of memory")
    content: str = Field(..., min_length=1, description="Primary textual content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Structured contextual metadata")
    source: str = Field(default="user", description="Originator of memory (e.g. user, task, runtime)")
    task_id: Optional[str] = Field(default=None, description="Optional associated task identifier")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Creation ISO 8601 UTC timestamp",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Last update ISO 8601 UTC timestamp",
    )
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Relevance importance weight between 0.0 and 1.0",
    )
    tags: List[str] = Field(default_factory=list, description="Categorical tags for filtering and indexing")
    expires_at: Optional[str] = Field(default=None, description="Optional expiration ISO 8601 UTC timestamp")


class MemoryCreateRequest(BaseModel):
    """Validation schema for storing a new memory entry."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, description="Content to store")
    memory_type: MemoryType = Field(default=MemoryType.FACT, description="Memory category")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Context metadata")
    source: str = Field(default="user", description="Source of memory")
    task_id: Optional[str] = Field(default=None, description="Optional task ID")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Importance weight")
    tags: List[str] = Field(default_factory=list, description="Descriptive tags")
    expires_at: Optional[str] = Field(default=None, description="Expiration timestamp")
    allow_duplicate: bool = Field(default=False, description="Whether to bypass deduplication check")


class MemoryUpdateRequest(BaseModel):
    """Validation schema for modifying an existing memory entry."""

    model_config = ConfigDict(extra="forbid")

    content: Optional[str] = Field(default=None, min_length=1)
    metadata: Optional[Dict[str, Any]] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tags: Optional[List[str]] = None
    expires_at: Optional[str] = None


class MemorySearchResult(BaseModel):
    """Scored memory search outcome."""

    model_config = ConfigDict(extra="ignore")

    entry: MemoryEntry
    relevance_score: float = Field(..., ge=0.0, description="Calculated deterministic relevance score")
    match_reasons: List[str] = Field(default_factory=list, description="Breakdown of score contributors")
