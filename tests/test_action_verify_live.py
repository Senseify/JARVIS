"""Live end-to-end bridge tests for screen observation and action verification over WebSocket."""

import asyncio
import socket
from typing import AsyncGenerator
import pytest
import uvicorn
import httpx

from core.main import RuntimeContainer, create_app
from windows_agent.agent import WindowsAgent


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def running_server(tmp_path) -> AsyncGenerator[tuple[str, RuntimeContainer], None]:
    port = get_free_port()
    db_file = str(tmp_path / "action_verify_live.db")
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
async def test_live_screen_capture_and_action_verify(running_server):
    """Verify live screen capture and Action -> Observe -> Verify execution over WebSocket."""
    base_url, container = running_server
    port = base_url.split(":")[-1]
    core_ws_url = f"ws://127.0.0.1:{port}/ws/agent"

    device_id = "test-win-observer-01"
    agent = WindowsAgent(
        core_url=core_ws_url,
        device_id=device_id,
        hostname="DESKTOP-OBSERVE",
        heartbeat_interval=0.5,
    )

    await agent.start()
    for _ in range(30):
        if agent.is_connected and container.agent_bridge.is_connected(device_id):
            break
        await asyncio.sleep(0.1)

    assert agent.is_connected is True

    async with httpx.AsyncClient(base_url=base_url) as client:
        # 1. Dispatch screen.capture (full screen)
        cap_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "screen.capture", "parameters": {}},
        )
        assert cap_resp.status_code == 200
        cap_data = cap_resp.json()
        assert cap_data["success"] is True
        result = cap_data["result"]
        assert "capture_id" in result
        assert result["width"] > 0
        assert result["height"] > 0
        assert "file_path" in result
        # Ensure raw pixel arrays are not leaked through response
        assert "raw_bytes" not in result

        # 2. Dispatch screen.capture with bounded region
        region_resp = await client.post(
            f"/devices/{device_id}/command",
            json={
                "capability": "screen.capture",
                "parameters": {
                    "region": {"top": 10, "left": 10, "width": 200, "height": 150}
                },
            },
        )
        assert region_resp.status_code == 200
        reg_data = region_resp.json()
        assert reg_data["success"] is True
        assert reg_data["result"]["width"] <= 200
        assert reg_data["result"]["height"] <= 150

        # 3. Dispatch malformed screen.capture parameters
        bad_cap_resp = await client.post(
            f"/devices/{device_id}/command",
            json={
                "capability": "screen.capture",
                "parameters": {"monitor_index": -5},
            },
        )
        assert bad_cap_resp.status_code == 200
        bad_data = bad_cap_resp.json()
        assert bad_data["success"] is False
        assert "Invalid parameters" in bad_data["error"]

        # 4. Dispatch action.verify with passing condition (screen_dimensions)
        verify_ok_resp = await client.post(
            f"/devices/{device_id}/command",
            json={
                "capability": "action.verify",
                "parameters": {
                    "action_capability": "mouse.move",
                    "action_parameters": {"x": 250, "y": 250},
                    "expected_condition": "screen_dimensions",
                    "expected_value": 640,
                    "pre_observe": True,
                },
            },
        )
        assert verify_ok_resp.status_code == 200
        verify_ok_data = verify_ok_resp.json()
        assert verify_ok_data["success"] is True
        v_res = verify_ok_data["result"]
        assert v_res["verified"] is True
        assert v_res["action_receipt"]["success"] is True
        assert v_res["post_screen_state"] is not None
        assert v_res["pre_screen_state"] is not None

        # 5. Dispatch action.verify with failing condition (active window mismatch)
        verify_fail_resp = await client.post(
            f"/devices/{device_id}/command",
            json={
                "capability": "action.verify",
                "parameters": {
                    "action_capability": "mouse.move",
                    "action_parameters": {"x": 260, "y": 260},
                    "expected_condition": "active_window_title",
                    "expected_value": "DefinitivelyNonExistentWindow_987654321",
                    "pre_observe": False,
                },
            },
        )
        assert verify_fail_resp.status_code == 200
        verify_fail_data = verify_fail_resp.json()
        # Action succeeded physically, but verification failed -> overall success is False
        assert verify_fail_data["success"] is False
        fail_res = verify_fail_data["result"]
        assert fail_res["verified"] is False
        assert fail_res["failure_reason"] is not None
        assert "DefinitivelyNonExistentWindow_987654321" in fail_res["failure_reason"]
        assert fail_res["pre_screen_state"] is None

        # 6. Dispatch malformed action.verify request
        bad_verify_resp = await client.post(
            f"/devices/{device_id}/command",
            json={
                "capability": "action.verify",
                "parameters": {
                    "action_capability": "",  # invalid empty string
                    "expected_condition": "screen_dimensions",
                    "expected_value": 100,
                },
            },
        )
        assert bad_verify_resp.status_code == 200
        bad_verify_data = bad_verify_resp.json()
        assert bad_verify_data["success"] is False
        assert "Invalid parameters" in bad_verify_data["error"]

    await agent.stop()


@pytest.mark.asyncio
async def test_core_operation_without_connected_agent(running_server):
    """Verify Core remains fully operational when target agent is not connected."""
    base_url, container = running_server

    async with httpx.AsyncClient(base_url=base_url) as client:
        # 1. Querying an unconnected device returns cleanly with 503 Service Unavailable
        resp = await client.post(
            "/devices/disconnected-agent-id/command",
            json={"capability": "screen.capture", "parameters": {}},
        )
        assert resp.status_code in (404, 503)

        # 2. General core health, info, and tasks endpoints continue functioning
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json()["status"] == "ok"

        info_resp = await client.get("/info")
        assert info_resp.status_code == 200

        devices_resp = await client.get("/devices")
        assert devices_resp.status_code == 200
        assert isinstance(devices_resp.json(), list)
