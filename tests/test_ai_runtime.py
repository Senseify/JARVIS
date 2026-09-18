"""Tests for local model provider runtime, capabilities, and ModelManager."""

import pytest
from core.ai.local_provider import DeterministicLocalProvider, LocalModelProvider
from core.ai.manager import ModelManager
from core.models.ai import ChatMessage, ModelRequest, ModelRole


@pytest.mark.asyncio
async def test_deterministic_local_provider_capabilities():
    provider = DeterministicLocalProvider()
    caps = provider.get_capabilities()

    assert caps.local_only is True
    assert caps.supports_tools is True
    assert caps.context_window >= 4096

    health = await provider.check_health()
    assert health is True

    info = provider.get_runtime_info()
    assert info.status == "ready"
    assert info.loaded is True


@pytest.mark.asyncio
async def test_deterministic_provider_conversation():
    provider = DeterministicLocalProvider()
    req = ModelRequest(
        messages=[
            ChatMessage(role=ModelRole.USER, content="Who are you?"),
        ]
    )

    resp = await provider.generate(req)
    assert "JARVIS" in resp.content
    assert len(resp.tool_calls) == 0
    assert resp.finish_reason == "stop"
    assert resp.duration_ms >= 0


@pytest.mark.asyncio
async def test_deterministic_provider_multi_step_tool_extraction():
    provider = DeterministicLocalProvider()
    req = ModelRequest(
        messages=[
            ChatMessage(role=ModelRole.USER, content="Open Notepad and type hello world"),
        ]
    )

    resp = await provider.generate(req)
    assert len(resp.tool_calls) == 2
    assert resp.tool_calls[0].tool == "app.launch"
    assert resp.tool_calls[0].arguments["app"] == "notepad"
    assert resp.tool_calls[1].tool == "keyboard.type"
    assert resp.tool_calls[1].arguments["text"] == "hello world"


@pytest.mark.asyncio
async def test_deterministic_provider_mouse_tools():
    provider = DeterministicLocalProvider()
    req = ModelRequest(
        messages=[
            ChatMessage(role=ModelRole.USER, content="Move mouse to 500 300 and click"),
        ]
    )

    resp = await provider.generate(req)
    assert len(resp.tool_calls) >= 1
    assert any(c.tool == "mouse.move" for c in resp.tool_calls)


@pytest.mark.asyncio
async def test_model_manager_registration_and_switching():
    manager = ModelManager()

    providers = manager.list_providers()
    assert len(providers) >= 2
    assert manager.get_active_provider_name() == "deterministic"

    info = manager.get_active_info()
    assert info.model_id == "jarvis-deterministic-v1"

    # Switch provider
    manager.set_active_provider("ollama_local")
    assert manager.get_active_provider_name() == "ollama_local"

    # Switch to non-existent raises ValueError
    with pytest.raises(ValueError):
        manager.set_active_provider("non_existent_provider")

    # Switch back
    manager.set_active_provider("deterministic")
    req = ModelRequest(messages=[ChatMessage(role=ModelRole.USER, content="Hello")])
    resp = await manager.generate(req)
    assert resp.content != ""


@pytest.mark.asyncio
async def test_local_model_provider_offline_graceful():
    # Attempting to query an unreachable local port should handle error gracefully without crash
    provider = LocalModelProvider(base_url="http://127.0.0.1:59999/v1", timeout=0.5)
    health = await provider.check_health()
    assert health is False

    req = ModelRequest(
        messages=[ChatMessage(role=ModelRole.USER, content="Test prompt")],
        timeout_seconds=1.0,
    )
    resp = await provider.generate(req)
    assert resp.finish_reason == "error"
    assert "unavailable" in resp.content.lower() or "error" in resp.content.lower()
