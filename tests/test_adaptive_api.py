"""Tests for adaptive device and model intelligence REST endpoints."""

from starlette.testclient import TestClient
from core.main import RuntimeContainer, create_app


def test_adaptive_model_and_device_endpoints():
    rt = RuntimeContainer()
    app = create_app(rt)
    client = TestClient(app)

    # 1. Device status
    dev_resp = client.get("/api/v1/devices/status")
    assert dev_resp.status_code == 200
    dev_data = dev_resp.json()
    assert "os_type" in dev_data
    assert "cpu_model" in dev_data
    assert "ram_total_mb" in dev_data
    assert len(dev_data["gpus"]) >= 1

    # 2. Model registry
    reg_resp = client.get("/api/v1/models/registry")
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert "models" in reg_data
    assert "discovery" in reg_data
    assert any(m["model_id"] == "deterministic-local-v1" for m in reg_data["models"])

    # 3. Model routing POST
    route_resp = client.post(
        "/api/v1/models/route",
        json={
            "requires_tools": True,
            "requires_vision": False,
            "requires_coding": True,
            "preferred_latency": "balanced",
        },
    )
    assert route_resp.status_code == 200
    route_data = route_resp.json()
    assert "selected_model_id" in route_data
    assert "routing_reason" in route_data
    assert "fallback_used" in route_data

    # 4. System status includes device_hub and model_intelligence
    sys_resp = client.get("/system/status")
    assert sys_resp.status_code == 200
    sys_data = sys_resp.json()
    assert "device_hub" in sys_data
    assert "model_intelligence" in sys_data
    assert sys_data["device_hub"]["os_type"] in ("darwin", "windows", "linux")
