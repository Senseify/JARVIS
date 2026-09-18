"""Typed communication protocol models for Core <-> Windows Agent interactions."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field


class MessageType(str, Enum):
    """Enumeration of message types exchanged over the agent bridge."""

    REGISTER = "register"
    REGISTER_ACK = "register_ack"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    COMMAND_REQUEST = "command_request"
    COMMAND_RESULT = "command_result"
    DISCONNECT = "disconnect"
    ERROR = "error"


class AgentRegistrationPayload(BaseModel):
    """Payload sent by an agent during initial connection handshake."""

    model_config = ConfigDict(extra="ignore")

    device_id: str = Field(..., min_length=1)
    hostname: str = Field(..., min_length=1)
    platform: str = Field(..., min_length=1)
    agent_version: str = Field(..., min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegisterAckPayload(BaseModel):
    """Payload sent by Core acknowledging agent registration."""

    model_config = ConfigDict(extra="ignore")

    status: str = "registered"
    device_id: str
    heartbeat_interval_seconds: float = 5.0
    server_version: str
    message: str = "Registration successful"


class HeartbeatPayload(BaseModel):
    """Periodic health ping sent from Agent to Core."""

    model_config = ConfigDict(extra="ignore")

    device_id: str
    uptime_seconds: float
    status: str = "online"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class HeartbeatAckPayload(BaseModel):
    """Acknowledgement of heartbeat sent from Core to Agent."""

    model_config = ConfigDict(extra="ignore")

    device_id: str
    status: str = "acknowledged"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommandRequestPayload(BaseModel):
    """Command invocation request sent from Core to Agent."""

    model_config = ConfigDict(extra="ignore")

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: str
    capability: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommandResultPayload(BaseModel):
    """Execution result returned from Agent to Core."""

    model_config = ConfigDict(extra="ignore")

    request_id: str
    device_id: str
    capability: str
    success: bool
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    execution_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommandDispatchRequest(BaseModel):
    """Schema for dispatching a command to a device via the Core REST API."""

    model_config = ConfigDict(extra="ignore")

    capability: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout: float = Field(default=10.0, ge=0.1, le=60.0)


class AgentMessage(BaseModel):
    """Top-level envelope for all messages between Core and Agents."""

    model_config = ConfigDict(extra="ignore")

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    message_type: MessageType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
