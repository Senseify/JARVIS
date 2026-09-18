"""End-to-end integration tests connecting WindowsAgent to JARVIS Core over live WebSocket."""

import asyncio
import socket
from typing import AsyncGenerator
import pytest
import uvicorn
import httpx

from core.constants import DeviceStatus
from core.main import RuntimeContainer, create_app
from windows_agent.agent import WindowsAgent


def get_free_port() -> int:
    """Find an available local port for the test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def running_server(tmp_path) -> AsyncGenerator[tuple[str, RuntimeContainer], None]:
    """Start an isolated JARVIS Core FastAPI server on an ephemeral port."""
    port = get_free_port()
    db_file = str(tmp_path / "integration_core.db")
    container = RuntimeContainer(db_path=db_file)
    app = create_app(container=container)

    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        lifespan="on",
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait for server startup
    base_url = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient(base_url=base_url) as client:
        for _ in range(50):
            try:
                res = await client.get("/health")
                if res.status_code == 200:
                    break
            except Exception:
                await asyncio.sleep(0.05)

    yield base_url, container

    server.should_exit = True
    await server_task


@pytest.mark.asyncio
async def test_windows_agent_full_lifecycle(running_server):
    """End-to-end live verification of Windows Agent connecting to Core,
    registering capabilities, exchanging heartbeats, executing commands,
    and cleanly disconnecting.
    """
    base_url, container = running_server
    port = base_url.split(":")[-1]
    core_ws_url = f"ws://127.0.0.1:{port}/ws/agent"

    device_id = "test-windows-agent-01"
    agent = WindowsAgent(
        core_url=core_ws_url,
        device_id=device_id,
        hostname="TEST-WIN-HOST",
        heartbeat_interval=0.5,  # fast heartbeats for testing
    )

    # 1. Start agent and wait for connection & registration
    await agent.start()
    for _ in range(30):
        if agent.is_connected and container.agent_bridge.is_connected(device_id):
            break
        await asyncio.sleep(0.1)

    assert agent.is_connected is True
    assert container.agent_bridge.is_connected(device_id) is True

    # 2. Verify device registered in Core DeviceRegistry
    device = await container.device_registry.get(device_id)
    assert device is not None
    assert device.name == "TEST-WIN-HOST"
    assert device.status == DeviceStatus.ONLINE
    assert "agent.ping" in device.capabilities
    assert "system.info" in device.capabilities
    assert "agent.status" in device.capabilities

    # 3. Verify Heartbeat updates last_seen
    initial_last_seen = device.last_seen
    await asyncio.sleep(0.8)  # Allow at least 1 heartbeat
    updated_device = await container.device_registry.get(device_id)
    assert updated_device.last_seen >= initial_last_seen

    # 4. Command execution: agent.ping
    ping_result = await container.agent_bridge.send_command(
        device_id=device_id,
        capability="agent.ping",
        parameters={},
        timeout=3.0,
    )
    assert ping_result.success is True
    assert ping_result.capability == "agent.ping"
    assert ping_result.device_id == device_id
    assert ping_result.result["pong"] is True
    assert "timestamp" in ping_result.result

    # 5. Command execution: system.info
    info_result = await container.agent_bridge.send_command(
        device_id=device_id,
        capability="system.info",
        parameters={},
        timeout=3.0,
    )
    assert info_result.success is True
    assert "platform" in info_result.result
    assert "python_version" in info_result.result
    assert "architecture" in info_result.result

    # 6. Command execution: agent.status
    status_result = await container.agent_bridge.send_command(
        device_id=device_id,
        capability="agent.status",
        parameters={},
        timeout=3.0,
    )
    assert status_result.success is True
    assert status_result.result["status"] == "online"
    assert status_result.result["uptime_seconds"] >= 0.0

    # 7. Command dispatch via Core HTTP REST API
    async with httpx.AsyncClient(base_url=base_url) as client:
        http_cmd_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "agent.ping", "parameters": {}},
        )
        assert http_cmd_resp.status_code == 200
        http_data = http_cmd_resp.json()
        assert http_data["success"] is True
        assert http_data["result"]["pong"] is True

        # 8. Unsupported capability rejection via API
        bad_cmd_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "unsupported.action", "parameters": {}},
        )
        assert bad_cmd_resp.status_code == 400
        assert "not supported" in bad_cmd_resp.json()["detail"]

    # 9. Clean disconnect
    await agent.stop()
    await asyncio.sleep(0.2)
    assert agent.is_connected is False
    assert container.agent_bridge.is_connected(device_id) is False

    # Verify device status marked OFFLINE in Core
    offline_device = await container.device_registry.get(device_id)
    assert offline_device.status == DeviceStatus.OFFLINE


@pytest.mark.asyncio
async def test_core_operates_independently_without_agent(running_server):
    """Verify JARVIS Core is fully functional and responsive when no agent is connected."""
    base_url, container = running_server
    async with httpx.AsyncClient(base_url=base_url) as client:
        # Health & Info work
        h = await client.get("/health")
        assert h.status_code == 200

        info = await client.get("/info")
        assert info.status_code == 200
        assert info.json()["connected_agents"] == []

        # Core runtime tasks run normally
        t_resp = await client.post("/tasks", json={"input": "Core standalone test", "execute_immediately": True})
        assert t_resp.status_code == 201
        task_id = t_resp.json()["id"]

        await asyncio.sleep(0.4)
        get_t = await client.get(f"/tasks/{task_id}")
        assert get_t.status_code == 200
        assert get_t.json()["status"] == "completed"

        # Attempting command to non-connected device returns 503 Service Unavailable
        cmd_resp = await client.post(
            "/devices/nonexistent-agent/command",
            json={"capability": "agent.ping"},
        )
        assert cmd_resp.status_code == 503
