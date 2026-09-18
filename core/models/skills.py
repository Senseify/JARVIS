"""Structured data models for JARVIS OS Skills Engine."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SkillStep(BaseModel):
    """Definition of a single atomic or composite step in a skill workflow."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(..., min_length=1, max_length=64, description="Unique identifier for the step within the skill")
    name: str = Field(default="", max_length=128, description="Human-readable step name")
    capability: str = Field(..., min_length=1, max_length=64, description="Target capability or tool name")
    parameters_template: Dict[str, Any] = Field(default_factory=dict, description="Parameters with variable substitution placeholders")
    expected_condition: Optional[str] = Field(default=None, max_length=64, description="Optional verification condition")
    expected_value: Optional[Any] = Field(default=None, description="Optional expected value for verification condition")
    timeout: float = Field(default=10.0, gt=0.0, le=300.0, description="Step execution timeout in seconds")
    continue_on_failure: bool = Field(default=False, description="Whether to continue subsequent steps if this step fails")

    @field_validator("step_id", "capability")
    @classmethod
    def sanitize_identifiers(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Identifier cannot be empty or whitespace only.")
        return cleaned


class SkillDefinition(BaseModel):
    """Metadata, requirements, and ordered workflow steps defining a reusable Skill."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=64, description="Unique alphanumeric identifier for the skill")
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable skill name")
    description: str = Field(default="", max_length=500, description="Detailed explanation of the skill workflow")
    version: str = Field(default="0.1.0", max_length=32, description="Semantic version of the skill definition")
    required_capabilities: List[str] = Field(default_factory=list, description="Capabilities prerequisite to executing this skill")
    steps: List[SkillStep] = Field(..., min_length=1, description="Ordered sequence of steps to execute")
    timeout: float = Field(default=30.0, gt=0.0, le=600.0, description="Maximum total skill execution timeout in seconds")
    verification_requirements: Dict[str, Any] = Field(default_factory=dict, description="Top-level verification requirements")
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="Specification of expected input parameters")
    output_schema: Dict[str, Any] = Field(default_factory=dict, description="Specification of produced output parameters")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extension metadata")

    @field_validator("id")
    @classmethod
    def sanitize_id(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("Skill id cannot be empty.")
        return cleaned


class SkillStepResult(BaseModel):
    """Execution receipt and outcome for an individual skill step."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    capability: str
    status: str = Field(default="success", description="Status: 'success', 'failed', or 'skipped'")
    success: bool = True
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = Field(default=0.0, ge=0.0)
    verified: Optional[bool] = None
    verification_details: Optional[Dict[str, Any]] = None


class SkillExecution(BaseModel):
    """Runtime tracking record for an active or completed skill execution."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_id: str
    status: str = Field(default="pending", description="Status: 'pending', 'running', 'completed', 'failed', 'timed_out'")
    inputs: Dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    step_results: List[SkillStepResult] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    memory_id: Optional[str] = None


class SkillResult(BaseModel):
    """Structured final output returned upon completion of a skill execution."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    skill_id: str
    success: bool
    status: str = Field(description="'completed', 'failed', or 'timed_out'")
    step_results: List[SkillStepResult] = Field(default_factory=list)
    output: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = Field(default=0.0, ge=0.0)
    memory_persisted: bool = False
    memory_id: Optional[str] = None


class SkillExecuteRequest(BaseModel):
    """Request payload for executing a skill via REST API or runtime dispatch."""

    model_config = ConfigDict(extra="forbid")

    inputs: Dict[str, Any] = Field(default_factory=dict, description="Input parameters for the skill workflow")
    device_id: Optional[str] = Field(default=None, description="Target machine agent device ID")
    task_id: Optional[str] = Field(default=None, description="Optional associated task ID for memory attribution")
