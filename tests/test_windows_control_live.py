"""Live end-to-end bridge tests for desktop automation commands over WebSocket."""

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
    db_file = str(tmp_path / "control_live.db")
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
async def test_live_desktop_automation_commands(running_server):
    """Verify live Core-to-Agent command dispatch for mouse, keyboard, window, and app capabilities."""
    base_url, container = running_server
    port = base_url.split(":")[-1]
    core_ws_url = f"ws://127.0.0.1:{port}/ws/agent"

    device_id = "test-win-controller-01"
    agent = WindowsAgent(
        core_url=core_ws_url,
        device_id=device_id,
        hostname="DESKTOP-CONTROL",
        heartbeat_interval=0.5,
    )

    await agent.start()
    for _ in range(30):
        if agent.is_connected and container.agent_bridge.is_connected(device_id):
            break
        await asyncio.sleep(0.1)

    assert agent.is_connected is True

    async with httpx.AsyncClient(base_url=base_url) as client:
        # 1. Dispatch mouse.move
        move_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "mouse.move", "parameters": {"x": 300, "y": 400}},
        )
        assert move_resp.status_code == 200
        move_data = move_resp.json()
        assert move_data["success"] is True
        assert move_data["result"]["capability"] == "mouse.move"
        assert move_data["result"]["x"] == 300
        assert move_data["result"]["y"] == 400

        # 2. Dispatch mouse.click
        click_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "mouse.click", "parameters": {"button": "left", "clicks": 1}},
        )
        assert click_resp.status_code == 200
        click_data = click_resp.json()
        assert click_data["success"] is True
        assert click_data["result"]["button"] == "left"

        # 3. Dispatch keyboard.type
        type_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "keyboard.type", "parameters": {"text": "Autonomous Agent Input"}},
        )
        assert type_resp.status_code == 200
        type_data = type_resp.json()
        assert type_data["success"] is True
        assert type_data["result"]["chars_typed"] == len("Autonomous Agent Input")

        # 4. Dispatch keyboard.hotkey
        hotkey_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "keyboard.hotkey", "parameters": {"keys": ["ctrl", "a"]}},
        )
        assert hotkey_resp.status_code == 200
        hotkey_data = hotkey_resp.json()
        assert hotkey_data["success"] is True

        # 5. Dispatch window.list
        win_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "window.list", "parameters": {"include_invisible": False}},
        )
        assert win_resp.status_code == 200
        win_data = win_resp.json()
        assert win_data["success"] is True
        assert "windows" in win_data["result"]

        # 6. Dispatch app.launch for allowlisted app
        launch_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "app.launch", "parameters": {"app_name": "notepad"}},
        )
        assert launch_resp.status_code == 200
        launch_data = launch_resp.json()
        assert launch_data["success"] is True
        assert launch_data["result"]["app_name"] == "notepad"

        # 7. Dispatch app.launch for unallowlisted app -> Expect failure
        bad_launch_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "app.launch", "parameters": {"app_name": "powershell"}},
        )
        assert bad_launch_resp.status_code == 200  # HTTP succeeded, but command result has success=False
        bad_data = bad_launch_resp.json()
        assert bad_data["success"] is False
        assert "not authorized" in bad_data["error"]

        # 8. Malformed coordinates -> Expect failure
        invalid_coords_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "mouse.move", "parameters": {"x": -100, "y": 200}},
        )
        assert invalid_coords_resp.status_code == 200
        invalid_data = invalid_coords_resp.json()
        assert invalid_data["success"] is False
        assert "Invalid parameters" in invalid_data["error"]

    await agent.stop()
