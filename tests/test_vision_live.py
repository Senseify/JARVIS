"""Live end-to-end bridge tests for vision capabilities (screen.ocr, screen.ui_elements, screen.understand) over WebSocket."""

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
    db_file = str(tmp_path / "vision_live.db")
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
async def test_live_vision_capabilities_over_bridge(running_server):
    """Verify live Core-to-Agent dispatch of screen.ocr, screen.ui_elements, and screen.understand."""
    base_url, container = running_server
    port = base_url.split(":")[-1]
    core_ws_url = f"ws://127.0.0.1:{port}/ws/agent"

    device_id = "test-win-vision-01"
    agent = WindowsAgent(
        core_url=core_ws_url,
        device_id=device_id,
        hostname="DESKTOP-VISION",
        heartbeat_interval=0.5,
    )

    await agent.start()
    for _ in range(30):
        if agent.is_connected and container.agent_bridge.is_connected(device_id):
            break
        await asyncio.sleep(0.1)

    assert agent.is_connected is True

    async with httpx.AsyncClient(base_url=base_url) as client:
        # 1. Dispatch screen.ocr without observation_id (triggers auto-capture)
        ocr_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "screen.ocr", "parameters": {}},
        )
        assert ocr_resp.status_code == 200
        ocr_data = ocr_resp.json()
        assert ocr_data["success"] is True
        ocr_res = ocr_data["result"]
        captured_obs_id = ocr_res["observation_id"]
        assert captured_obs_id is not None
        assert isinstance(ocr_res["text_regions"], list)
        assert "count" in ocr_res

        # 2. Dispatch screen.ocr referencing existing observation_id (uses cached / stored observation)
        ocr_reuse_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "screen.ocr", "parameters": {"observation_id": captured_obs_id}},
        )
        assert ocr_reuse_resp.status_code == 200
        ocr_reuse_data = ocr_reuse_resp.json()
        assert ocr_reuse_data["success"] is True
        assert ocr_reuse_data["result"]["observation_id"] == captured_obs_id

        # 3. Dispatch malformed screen.ocr request (unexpected extra parameter)
        bad_ocr_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "screen.ocr", "parameters": {"unexpected_key": 123}},
        )
        assert bad_ocr_resp.status_code == 200
        bad_ocr_data = bad_ocr_resp.json()
        assert bad_ocr_data["success"] is False
        assert "Invalid parameters" in bad_ocr_data["error"]

        # 4. Dispatch screen.ui_elements
        ui_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "screen.ui_elements", "parameters": {}},
        )
        assert ui_resp.status_code == 200
        ui_data = ui_resp.json()
        assert ui_data["success"] is True
        assert isinstance(ui_data["result"]["ui_elements"], list)

        # 5. Dispatch malformed screen.ui_elements
        bad_ui_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "screen.ui_elements", "parameters": {"extra_field": "bad"}},
        )
        assert bad_ui_resp.status_code == 200
        bad_ui_data = bad_ui_resp.json()
        assert bad_ui_data["success"] is False
        assert "Invalid parameters" in bad_ui_data["error"]

        # 6. Dispatch screen.understand
        und_resp = await client.post(
            f"/devices/{device_id}/command",
            json={"capability": "screen.understand", "parameters": {}},
        )
        assert und_resp.status_code == 200
        und_data = und_resp.json()
        assert und_data["success"] is True
        und_res = und_data["result"]
        assert "observation_id" in und_res
        assert "screen_state" in und_res
        assert "text_regions" in und_res
        assert "ui_elements" in und_res

        # 7. Dispatch action.verify with vision check (text_absent)
        act_ver_absent = await client.post(
            f"/devices/{device_id}/command",
            json={
                "capability": "action.verify",
                "parameters": {
                    "action_capability": "mouse.move",
                    "action_parameters": {"x": 200, "y": 200},
                    "expected_condition": "text_absent",
                    "expected_value": "CriticalFatalKernelError_123456789",
                    "pre_observe": False,
                },
            },
        )
        assert act_ver_absent.status_code == 200
        ver_abs_data = act_ver_absent.json()
        assert ver_abs_data["success"] is True
        assert ver_abs_data["result"]["verified"] is True

        # 8. Dispatch action.verify with failing vision check (text_present expecting imaginary string)
        act_ver_fail = await client.post(
            f"/devices/{device_id}/command",
            json={
                "capability": "action.verify",
                "parameters": {
                    "action_capability": "mouse.move",
                    "action_parameters": {"x": 210, "y": 210},
                    "expected_condition": "text_present",
                    "expected_value": "ImaginaryTextThatDoesNotExist_987654321",
                    "pre_observe": False,
                },
            },
        )
        assert act_ver_fail.status_code == 200
        ver_fail_data = act_ver_fail.json()
        # Verification failed -> command success is False, honest failure reported
        assert ver_fail_data["success"] is False
        assert ver_fail_data["result"]["verified"] is False
        assert "not found" in ver_fail_data["result"]["failure_reason"]

    await agent.stop()
