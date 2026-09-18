"""Strict Pydantic models for AI runtime, local providers, and reasoning engine."""

from enum import Enum
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ModelRole(str, Enum):
    """Role in a conversational turn."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCallDefinition(BaseModel):
    """Structured tool call invocation produced by reasoning engine or model."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    tool: str = Field(..., min_length=1, description="Registered tool name (e.g. app.launch)")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Validated argument dictionary")


class ChatMessage(BaseModel):
    """Structured message in a conversation or model prompt."""

    model_config = ConfigDict(extra="forbid")

    role: ModelRole
    content: str = Field(default="")
    tool_calls: list[ToolCallDefinition] | None = Field(default=None)
    name: str | None = Field(default=None)


class ModelCapabilities(BaseModel):
    """Capabilities and constraints advertised by a model provider."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    supports_tools: bool = True
    supports_vision: bool = False
    supports_streaming: bool = True
    context_window: int = Field(default=8192, ge=512)
    local_only: bool = True
    description: str = ""


class ModelRuntimeInfo(BaseModel):
    """Diagnostic state of the active model runtime."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    provider_type: str
    status: str = "ready"
    device: str = "local"
    loaded: bool = True
    memory_usage_mb: float = 0.0
    endpoint: str | None = None


class ModelRequest(BaseModel):
    """Inference request passed to a model provider."""

    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(..., min_length=1)
    tools: list[dict[str, Any]] | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    stop_sequences: list[str] | None = None
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    stream: bool = False


class ModelResponse(BaseModel):
    """Inference response returned by a model provider."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="")
    tool_calls: list[ToolCallDefinition] = Field(default_factory=list)
    finish_reason: str = Field(default="stop")
    usage: dict[str, int] = Field(default_factory=dict)
    model_name: str = Field(default="local-model")
    duration_ms: float = Field(default=0.0, ge=0.0)


class ChatRequest(BaseModel):
    """User conversational or instruction request to JARVIS."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1)
    session_id: str = Field(default="default")
    device_id: str | None = None
    context_override: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    """Structured response from JARVIS Reasoning Engine."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    message: str
    plan_id: str | None = None
    requires_action: bool = False
    tool_calls: list[ToolCallDefinition] = Field(default_factory=list)
    model_used: str = "local-reasoner"
    duration_ms: float = 0.0
