"""Tests for Phase 3 typed protocol schemas and message validation."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from core.models.protocol import (
    AgentMessage,
    AgentRegistrationPayload,
    CommandDispatchRequest,
    CommandRequestPayload,
    CommandResultPayload,
    HeartbeatAckPayload,
    HeartbeatPayload,
    MessageType,
    RegisterAckPayload,
)


def test_agent_registration_payload():
    """Verify registration payload fields and serialization."""
    reg = AgentRegistrationPayload(
        device_id="win-pc-01",
        hostname="WORKSTATION-01",
        platform="Windows",
        agent_version="0.1.0",
        capabilities=["agent.ping", "system.info"],
        metadata={"os_build": "19045"},
    )
    data = reg.model_dump()
    assert data["device_id"] == "win-pc-01"
    assert data["platform"] == "Windows"
    assert "agent.ping" in data["capabilities"]
    assert data["metadata"]["os_build"] == "19045"


def test_register_ack_payload():
    """Verify registration ack payload defaults."""
    ack = RegisterAckPayload(
        device_id="win-pc-01",
        server_version="0.1.0",
    )
    assert ack.status == "registered"
    assert ack.heartbeat_interval_seconds == 5.0
    assert ack.device_id == "win-pc-01"


def test_command_request_and_result_correlation():
    """Verify request ID is preserved between command request and result."""
    req_id = str(uuid4())
    req = CommandRequestPayload(
        request_id=req_id,
        device_id="win-pc-01",
        capability="agent.ping",
        parameters={"test": 123},
    )

    result = CommandResultPayload(
        request_id=req.request_id,
        device_id=req.device_id,
        capability=req.capability,
        success=True,
        result={"pong": True},
    )

    assert result.request_id == req.request_id
    assert result.device_id == req.device_id
    assert result.success is True
    assert result.result == {"pong": True}


def test_agent_message_envelope():
    """Verify top-level AgentMessage envelope serialization and JSON round-trip."""
    corr_id = str(uuid4())
    msg = AgentMessage(
        correlation_id=corr_id,
        message_type=MessageType.HEARTBEAT,
        payload={"uptime": 42.5},
    )

    msg_json = msg.model_dump_json()
    parsed = json.loads(msg_json)

    assert parsed["correlation_id"] == corr_id
    assert parsed["message_type"] == "heartbeat"
    assert parsed["payload"]["uptime"] == 42.5
    assert "timestamp" in parsed
