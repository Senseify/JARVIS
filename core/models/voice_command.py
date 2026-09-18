"""Data models for JARVIS OS Voice Command Pipeline."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from core.models.voice import VoiceInput


class VoiceCommandIntentType(str, Enum):
    """Supported intent types recognized by the voice command pipeline."""

    APP_LAUNCH = "app_launch"
    KEYBOARD_TYPE = "keyboard_type"
    KEYBOARD_PRESS = "keyboard_press"
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    QUERY_TASK_STATUS = "query_task_status"
    QUERY_DEVICES = "query_devices"
    UNKNOWN = "unknown"


class VoiceCommandIntent(BaseModel):
    """Structured intent representation extracted from transcribed speech."""

    model_config = ConfigDict(extra="forbid")

    intent_type: VoiceCommandIntentType = Field(..., description="Classification category for the command")
    action_target: str = Field(default="", description="Primary entity or target of the action (e.g. app name, key, button)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Extracted typed parameters for action execution")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Parsing confidence score")
    matched_pattern: Optional[str] = Field(default=None, description="Grammar pattern or expression matched")


class VoiceCommand(BaseModel):
    """Parsed voice command ready for runtime dispatch."""

    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transcript: str = Field(..., description="Raw speech recognition transcript")
    intent: VoiceCommandIntent = Field(..., description="Understood intent and parameters")
    extracted_parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    task_id: Optional[str] = Field(default=None, description="Associated runtime task ID")
    device_id: Optional[str] = Field(default=None, description="Target machine agent device ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VoiceCommandResult(BaseModel):
    """Final outcome returned by the Voice Command Pipeline."""

    model_config = ConfigDict(extra="forbid")

    command_id: str
    transcript: str
    intent: Optional[VoiceCommandIntent] = None
    status: str = Field(description="Execution status: 'completed', 'failed', 'unrecognized', 'timed_out'")
    success: bool
    execution_result: Optional[Dict[str, Any]] = None
    response_text: str = Field(..., description="Concise verbal response text")
    synthesized_audio: Optional[str] = Field(default=None, description="Base64-encoded WAV speech audio of the response")
    task_id: Optional[str] = None
    verification_status: Optional[str] = Field(default=None, description="'verified', 'unverified', 'failed', 'not_applicable'")
    duration_ms: float = Field(default=0.0, ge=0.0)
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VoiceCommandRequest(BaseModel):
    """Payload for invoking a voice command via REST API."""

    model_config = ConfigDict(extra="forbid")

    voice_input: Optional[VoiceInput] = Field(default=None, description="Audio payload for speech recognition")
    text_override: Optional[str] = Field(default=None, description="Direct text transcript for testing or non-audio invocation")
    device_id: Optional[str] = Field(default=None, description="Target machine agent device ID")
    task_id: Optional[str] = Field(default=None, description="Optional caller-provided task correlation ID")
    synthesize_response: bool = Field(default=True, description="Whether to synthesize a spoken audio response")
