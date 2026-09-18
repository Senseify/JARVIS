"""Pydantic models for the centralized security policy and risk evaluation layer."""

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    """Action risk classification."""

    READ_ONLY = "read_only"  # Screen observation, window inspection, read queries
    LOW_RISK = "low_risk"    # Launching allowlisted applications, focus window
    MEDIUM_RISK = "medium_risk"  # Keyboard typing, mouse movement, clicks
    HIGH_RISK = "high_risk"  # System configuration changes, destructive writes
    BLOCKED = "blocked"      # Arbitrary shell execution, code evaluation, disallowed apps


class ActionPolicyEvaluation(BaseModel):
    """Result of evaluating a proposed action against security policy."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    risk_level: RiskLevel
    reason: str
    requires_confirmation: bool = False
    sanitized_arguments: dict[str, Any] = Field(default_factory=dict)


class SecurityPolicyConfig(BaseModel):
    """Configuration for security policy enforcement."""

    model_config = ConfigDict(extra="forbid")

    allowlisted_apps: list[str] = Field(
        default_factory=lambda: [
            "notepad",
            "calc",
            "calculator",
            "mspaint",
            "paint",
            "explorer",
            "edge",
            "chrome",
            "code",
        ]
    )
    blocked_tools: list[str] = Field(
        default_factory=lambda: [
            "shell.execute",
            "cmd.run",
            "powershell.run",
            "eval",
            "system.exec",
            "bash.exec",
            "sh.run",
        ]
    )
    max_typing_length: int = Field(default=10000, ge=1)
    allow_remote_control: bool = True
    require_confirmation_for_high_risk: bool = True
