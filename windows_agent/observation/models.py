"""Models and schemas for screen state, capture requests, and verification results."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CaptureRegion(BaseModel):
    """Bounding box region for partial screen capture."""

    model_config = ConfigDict(extra="forbid")

    top: int = Field(..., ge=0)
    left: int = Field(..., ge=0)
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)


class CaptureScreenParams(BaseModel):
    """Validation schema for screen.capture capability."""

    model_config = ConfigDict(extra="forbid")

    monitor_index: Optional[int] = Field(default=None, ge=1, description="1-indexed monitor, or None for primary/all")
    region: Optional[CaptureRegion] = Field(default=None, description="Optional bounding box region to crop")


class ScreenState(BaseModel):
    """Structured representation of observed screen state without transmitting raw pixels."""

    model_config = ConfigDict(extra="ignore")

    capture_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    width: int
    height: int
    monitor_index: int = 1
    active_window: Optional[Dict[str, Any]] = None
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    """Structured outcome of an automated verification check."""

    model_config = ConfigDict(extra="ignore")

    verification_id: str = Field(default_factory=lambda: str(uuid4()))
    check_type: str
    expected_condition: str
    observed_state: Any
    passed: bool
    failure_reason: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ActionVerifyParams(BaseModel):
    """Validation schema for action.verify (Action -> Observe -> Verify)."""

    model_config = ConfigDict(extra="forbid")

    action_capability: str = Field(..., min_length=1)
    action_parameters: Dict[str, Any] = Field(default_factory=dict)
    expected_condition: str = Field(..., min_length=1)
    expected_value: Any
    pre_observe: bool = False
