"""Tests for Core Skills REST API endpoints."""

from typing import Any, Dict
import pytest
from starlette.testclient import TestClient

from core.main import RuntimeContainer, create_app


@pytest.fixture
def api_client(tmp_path):
    db_file = str(tmp_path / "skills_api.db")
    container = RuntimeContainer(db_path=db_file)
    app = create_app(container=container)
    with TestClient(app) as client:
        yield client, container


def test_list_skills_api(api_client):
    """Verify GET /skills lists all registered built-in skills."""
    client, _ = api_client
    resp = client.get("/skills")
    assert resp.status_code == 200
    skills = resp.json()
    assert len(skills) >= 3
    skill_ids = [s["id"] for s in skills]
    assert "launch_and_verify" in skill_ids
    assert "type_and_verify" in skill_ids
    assert "click_and_verify" in skill_ids


def test_get_skill_api(api_client):
    """Verify GET /skills/{skill_id} returns details or 404."""
    client, _ = api_client

    resp = client.get("/skills/launch_and_verify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "launch_and_verify"
    assert "app.launch" in data["required_capabilities"]
    assert len(data["steps"]) >= 1

    resp_404 = client.get("/skills/unknown_skill_xyz")
    assert resp_404.status_code == 404


def test_execute_skill_api(api_client):
    """Verify POST /skills/{skill_id}/execute executes and returns SkillResult."""
    client, container = api_client

    # Inject mock dispatcher for deterministic execution
    async def mock_dispatcher(device_id: str, capability: str, params: Dict[str, Any], timeout: float):
        return {
            "success": True,
            "verified": True,
            "action_capability": "app.launch",
            "action_receipt": {"success": True},
        }

    container.skill_executor.command_dispatcher = mock_dispatcher

    # Execute valid request
    resp = client.post(
        "/skills/launch_and_verify/execute",
        json={
            "inputs": {"app_name": "notepad", "window_title": "Notepad"},
            "task_id": "api_test_task",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill_id"] == "launch_and_verify"
    assert data["success"] is True
    assert data["status"] == "completed"
    assert len(data["step_results"]) >= 1
    assert data["memory_persisted"] is True


def test_execute_skill_validation_and_errors(api_client):
    """Verify 404 for unknown skill and 400 for missing required inputs."""
    client, _ = api_client

    # Unknown skill -> 404
    resp_404 = client.post(
        "/skills/unknown_skill/execute",
        json={"inputs": {}},
    )
    assert resp_404.status_code == 404

    # Missing required parameter app_name -> 400
    resp_400 = client.post(
        "/skills/launch_and_verify/execute",
        json={"inputs": {}},
    )
    assert resp_400.status_code == 400
    assert "Missing required input parameter" in resp_400.json()["detail"]
