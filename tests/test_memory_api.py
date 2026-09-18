"""Tests for Core memory REST API endpoints."""

import pytest
from starlette.testclient import TestClient

from core.main import RuntimeContainer, create_app


@pytest.fixture
def api_client(tmp_path):
    db_file = str(tmp_path / "memory_api.db")
    container = RuntimeContainer(db_path=db_file)
    app = create_app(container=container)
    with TestClient(app) as client:
        yield client, container


def test_memory_crud_api(api_client):
    """Verify REST API lifecycle: create, get, patch, delete, search."""
    client, _ = api_client

    # 1. Create new memory entry
    create_resp = client.post(
        "/memories",
        json={
            "content": "User prefers dark mode across all interfaces.",
            "memory_type": "preference",
            "source": "user_ui",
            "importance": 0.8,
            "tags": ["ui", "theme", "preference"],
        },
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["is_new"] is True
    memory = data["memory"]
    memory_id = memory["id"]
    assert memory["content"] == "User prefers dark mode across all interfaces."
    assert memory["importance"] == 0.8
    assert "theme" in memory["tags"]

    # 2. Duplicate submission updates existing entry
    dup_resp = client.post(
        "/memories",
        json={
            "content": "user prefers dark mode across all interfaces.",
            "memory_type": "preference",
            "importance": 0.95,
            "tags": ["theme", "accessibility"],
        },
    )
    assert dup_resp.status_code == 201
    dup_data = dup_resp.json()
    assert dup_data["is_new"] is False
    assert dup_data["memory"]["id"] == memory_id
    assert dup_data["memory"]["importance"] == 0.95
    assert "accessibility" in dup_data["memory"]["tags"]

    # 3. Get by ID
    get_resp = client.get(f"/memories/{memory_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == memory_id

    # 4. Search memories
    search_resp = client.get("/memories?q=dark+mode")
    assert search_resp.status_code == 200
    search_results = search_resp.json()
    assert len(search_results) == 1
    assert search_results[0]["entry"]["id"] == memory_id
    assert search_results[0]["relevance_score"] > 0

    # 5. Search with filtering by type and tag
    tag_search = client.get("/memories?tag=accessibility&type=preference")
    assert tag_search.status_code == 200
    assert len(tag_search.json()) == 1

    # 6. Patch memory
    patch_resp = client.patch(
        f"/memories/{memory_id}",
        json={"content": "User prefers high-contrast dark mode.", "importance": 1.0},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["content"] == "User prefers high-contrast dark mode."
    assert patched["importance"] == 1.0

    # 7. Delete by ID
    del_resp = client.delete(f"/memories/{memory_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # Confirm 404 after deletion
    assert client.get(f"/memories/{memory_id}").status_code == 404


def test_memory_api_task_association_and_cleanup(api_client):
    """Verify storing task-associated memories and clearing by task."""
    client, _ = api_client

    # Create task memories
    client.post(
        "/memories",
        json={"content": "Context for task-alpha", "memory_type": "task_context", "task_id": "task-alpha"},
    )
    client.post(
        "/memories",
        json={"content": "Outcome for task-alpha", "memory_type": "outcome", "task_id": "task-alpha"},
    )
    client.post(
        "/memories",
        json={"content": "Context for task-beta", "memory_type": "task_context", "task_id": "task-beta"},
    )

    # Search by task_id
    alpha_memories = client.get("/memories?task_id=task-alpha").json()
    assert len(alpha_memories) == 2

    # Clear task-alpha
    del_task_resp = client.delete("/memories/task/task-alpha")
    assert del_task_resp.status_code == 200
    assert del_task_resp.json()["deleted_count"] == 2

    # Confirm task-alpha memories are gone, task-beta remains
    assert len(client.get("/memories?task_id=task-alpha").json()) == 0
    assert len(client.get("/memories?task_id=task-beta").json()) == 1


def test_memory_api_validation_errors(api_client):
    """Verify 422 Unprocessable Entity on malformed payloads."""
    client, _ = api_client

    # Empty content
    resp1 = client.post("/memories", json={"content": ""})
    assert resp1.status_code == 422

    # Invalid importance
    resp2 = client.post("/memories", json={"content": "Valid", "importance": 5.0})
    assert resp2.status_code == 422

    # Forbidden extra keys
    resp3 = client.post("/memories", json={"content": "Valid", "unauthorized_key": "bad"})
    assert resp3.status_code == 422

    # Nonexistent memory 404s
    assert client.get("/memories/nonexistent-id-123").status_code == 404
    assert client.patch("/memories/nonexistent-id-123", json={"content": "New"}).status_code == 404
    assert client.delete("/memories/nonexistent-id-123").status_code == 404
