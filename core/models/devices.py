"""Device models for authorized device management."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from pydantic import BaseModel, Field

from core.constants import DeviceStatus, DeviceType


class Device(BaseModel):
    """Abstraction for authorized devices connecting to JARVIS OS."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    device_type: DeviceType = DeviceType.GENERIC_HOST
    status: DeviceStatus = DeviceStatus.ONLINE
    capabilities: list[str] = Field(default_factory=list)
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceCreateRequest(BaseModel):
    """Schema for registering a new device."""

    id: str | None = None
    name: str = Field(..., min_length=1)
    device_type: DeviceType = DeviceType.GENERIC_HOST
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
