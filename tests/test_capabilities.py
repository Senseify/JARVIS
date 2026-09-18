"""Tests for Windows Agent capability system."""

import pytest
from windows_agent.capabilities import CapabilityRegistry


@pytest.mark.asyncio
async def test_default_capabilities_registration():
    """Verify built-in safe capabilities are registered on initialization."""
    registry = CapabilityRegistry(agent_version="0.1.0")
    caps = registry.list_capabilities()

    assert "agent.ping" in caps
    assert "system.info" in caps
    assert "agent.status" in caps
    assert registry.has_capability("agent.ping")
    assert not registry.has_capability("unsupported.tool")


@pytest.mark.asyncio
async def test_ping_capability():
    """Verify agent.ping returns valid pong and agent version."""
    registry = CapabilityRegistry(agent_version="0.1.0")
    result = await registry.execute("agent.ping", {})

    assert result["pong"] is True
    assert result["agent_version"] == "0.1.0"
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_system_info_capability():
    """Verify system.info returns real platform and environment information."""
    registry = CapabilityRegistry(agent_version="0.1.0")
    result = await registry.execute("system.info", {})

    assert "platform" in result
    assert "platform_release" in result
    assert "architecture" in result
    assert "python_version" in result
    assert result["agent_version"] == "0.1.0"
    assert isinstance(result["is_windows"], bool)


@pytest.mark.asyncio
async def test_agent_status_capability():
    """Verify agent.status returns uptime and capabilities list."""
    registry = CapabilityRegistry(agent_version="0.1.0")
    result = await registry.execute("agent.status", {})

    assert result["status"] == "online"
    assert result["uptime_seconds"] >= 0.0
    assert result["agent_version"] == "0.1.0"
    assert "agent.ping" in result["registered_capabilities"]


@pytest.mark.asyncio
async def test_unsupported_capability_rejection():
    """Verify attempting to execute an unregistered capability raises KeyError."""
    registry = CapabilityRegistry()
    with pytest.raises(KeyError) as exc_info:
        await registry.execute("malicious.shell", {})
    assert "Unsupported capability" in str(exc_info.value)


@pytest.mark.asyncio
async def test_custom_capability_extension():
    """Verify registry can be safely extended with new capabilities."""
    registry = CapabilityRegistry()

    async def custom_handler(params):
        return {"multiplied": params.get("value", 1) * 2}

    registry.register("math.double", custom_handler, "Doubles input number")
    assert registry.has_capability("math.double")

    res = await registry.execute("math.double", {"value": 21})
    assert res["multiplied"] == 42
