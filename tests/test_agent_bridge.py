"""Tests for AgentBridge WebSocket protocol handling and command dispatch."""

import json
from uuid import uuid4
import pytest
from starlette.testclient import TestClient

from core.constants import DeviceStatus
from core.main import RuntimeContainer, create_app
from core.models.protocol import (
    AgentMessage,
    AgentRegistrationPayload,
    CommandResultPayload,
    HeartbeatPayload,
    MessageType,
)


@pytest.fixture
def app_and_container(tmp_path):
    db_file = str(tmp_path / "bridge_test.db")
    container = RuntimeContainer(db_path=db_file)
    app = create_app(container=container)
    with TestClient(app) as client:
        yield app, client, container


def test_agent_registration_handshake(app_and_container):
    """Verify agent registration over WebSocket and REGISTER_ACK response."""
    _, client, container = app_and_container

    corr_id = str(uuid4())
    reg_payload = AgentRegistrationPayload(
        device_id="win-desk-01",
        hostname="DESKTOP-WIN",
        platform="Windows",
        agent_version="0.1.0",
        capabilities=["agent.ping", "system.info"],
    )

    reg_msg = AgentMessage(
        correlation_id=corr_id,
        message_type=MessageType.REGISTER,
        payload=reg_payload.model_dump(),
    )

    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text(reg_msg.model_dump_json())
        ack_text = ws.receive_text()
        ack_data = json.loads(ack_text)

        assert ack_data["correlation_id"] == corr_id
        assert ack_data["message_type"] == "register_ack"
        assert ack_data["payload"]["device_id"] == "win-desk-01"
        assert ack_data["payload"]["status"] == "registered"

        # Verify device is recorded in DeviceRegistry as ONLINE
        assert container.agent_bridge.is_connected("win-desk-01")


def test_agent_heartbeat_exchange(app_and_container):
    """Verify heartbeat pings update device state and receive HEARTBEAT_ACK."""
    _, client, container = app_and_container

    with client.websocket_connect("/ws/agent") as ws:
        # Register first
        reg_msg = AgentMessage(
            correlation_id="reg-1",
            message_type=MessageType.REGISTER,
            payload=AgentRegistrationPayload(
                device_id="win-heartbeat-01",
                hostname="DESKTOP-HB",
                platform="Windows",
                agent_version="0.1.0",
                capabilities=["agent.ping"],
            ).model_dump(),
        )
        ws.send_text(reg_msg.model_dump_json())
        ws.receive_text()  # Consume REGISTER_ACK

        # Send heartbeat
        hb_corr = str(uuid4())
        hb_msg = AgentMessage(
            correlation_id=hb_corr,
            message_type=MessageType.HEARTBEAT,
            payload=HeartbeatPayload(
                device_id="win-heartbeat-01",
                uptime_seconds=12.4,
            ).model_dump(),
        )
        ws.send_text(hb_msg.model_dump_json())

        hb_ack_text = ws.receive_text()
        hb_ack_data = json.loads(hb_ack_text)

        assert hb_ack_data["correlation_id"] == hb_corr
        assert hb_ack_data["message_type"] == "heartbeat_ack"
        assert hb_ack_data["payload"]["device_id"] == "win-heartbeat-01"


def test_agent_disconnect_handling(app_and_container):
    """Verify disconnecting marks device OFFLINE without crashing Core."""
    _, client, container = app_and_container

    with client.websocket_connect("/ws/agent") as ws:
        reg_msg = AgentMessage(
            correlation_id="reg-disc",
            message_type=MessageType.REGISTER,
            payload=AgentRegistrationPayload(
                device_id="win-disc-01",
                hostname="DESKTOP-DISC",
                platform="Windows",
                agent_version="0.1.0",
                capabilities=["agent.ping"],
            ).model_dump(),
        )
        ws.send_text(reg_msg.model_dump_json())
        ws.receive_text()
        assert container.agent_bridge.is_connected("win-disc-01")

    # Connection closed upon exiting with block
    assert not container.agent_bridge.is_connected("win-disc-01")


def test_malformed_registration_rejected(app_and_container):
    """Verify non-JSON or invalid initial messages are rejected with error."""
    _, client, _ = app_and_container

    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text("INVALID_NON_JSON")
        resp = ws.receive_text()
        data = json.loads(resp)
        assert data["message_type"] == "error"
        assert "Malformed registration" in data["error"]
