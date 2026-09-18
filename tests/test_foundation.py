"""Foundation tests verifying Phase 1 scaffold, configuration, and API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

import core
from core.config import Settings
from core.constants import AgentLoopState
from core.main import create_app


def test_package_version():
    """Verify core package exports a valid version string."""
    assert hasattr(core, "__version__")
    assert core.__version__ == "0.1.0"


def test_agent_loop_states():
    """Verify all required Agent Loop states exist."""
    expected_states = [
        "idle",
        "observe",
        "understand",
        "plan",
        "act",
        "verify",
        "recover",
        "remember",
    ]
    actual_states = [state.value for state in AgentLoopState]
    assert actual_states == expected_states


def test_settings_defaults():
    """Verify default core configuration settings."""
    settings = Settings()
    assert settings.app_name == "JARVIS OS"
    assert settings.app_version == "0.1.0"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_project_boundary_cleanliness():
    """Verify core constants and config contain no application-specific couplings."""
    settings = Settings()
    combined_text = (
        f"{settings.app_name} {settings.environment} "
        f"{' '.join(s.value for s in AgentLoopState)}"
    ).lower()

    # Boundary verification: No hardcoded third-party app couplings
    assert "marvel" not in combined_text
    assert "ascension" not in combined_text
    assert "unity" not in combined_text


@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify /health endpoint returns 200 OK and expected payload."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["app"] == "JARVIS OS"
        assert data["version"] == "0.1.0"
        assert "environment" in data


@pytest.mark.asyncio
async def test_info_endpoint():
    """Verify /info endpoint returns 200 OK and valid loop states."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert data["app"] == "JARVIS OS"
        assert data["version"] == "0.1.0"
        assert "agent_loop_states" in data
        assert "observe" in data["agent_loop_states"]
        assert "verify" in data["agent_loop_states"]
        assert "recover" in data["agent_loop_states"]
