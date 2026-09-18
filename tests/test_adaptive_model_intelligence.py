"""Comprehensive test suite for Adaptive Local Model & Device Intelligence subsystems."""

import pytest
from core.ai.discovery import EngineDiscovery
from core.ai.manager import ModelManager
from core.ai.model_registry import ModelCapabilitiesProfile, ModelDescriptor, ModelRegistry
from core.ai.model_router import ModelRouter, TaskRequirements
from core.devices.device_hub import DeviceHub, GpuInfo
from core.models.ai import ChatMessage, ModelRequest, ModelRole
from core.voice.wake_word import VoiceInterruptionController, VoiceState, WakeWordConfig, WakeWordDetector


def test_device_hub_probe():
    hub = DeviceHub()
    cap = hub.get_device_capability()
    assert cap.os_type in ("darwin", "windows", "linux")
    assert cap.cpu_cores_logical >= 1
    assert cap.ram_total_mb > 0
    assert len(cap.gpus) >= 1
    assert "local_inference" in cap.supported_features


def test_model_registry_crud():
    reg = ModelRegistry()
    # Bedrock model always present
    assert reg.get_model("deterministic-local-v1") is not None

    custom = ModelDescriptor(
        model_id="test/coder-7b",
        display_name="Test Coder 7B",
        engine_type="ollama",
        provider_name="ollama_local",
        capabilities=ModelCapabilitiesProfile(
            reasoning=True,
            coding=True,
            planning=True,
            tool_calling=True,
            vision=False,
            context_window=32768,
            latency_tier="balanced",
        ),
        parameter_size="7B",
        min_ram_mb=4096.0,
        status="available",
    )
    reg.register_model(custom)
    assert reg.get_model("test/coder-7b") is not None

    # Capability search
    coders = reg.find_by_capability(requires_coding=True)
    assert any(m.model_id == "test/coder-7b" for m in coders)

    reg.unregister_model("test/coder-7b")
    assert reg.get_model("test/coder-7b") is None


def test_model_router_capability_matching():
    hub = DeviceHub()
    reg = ModelRegistry()

    # Register mock models for testing
    reg.register_model(
        ModelDescriptor(
            model_id="test/fast-mini",
            display_name="Fast Mini 1B",
            engine_type="ollama",
            provider_name="ollama_local",
            capabilities=ModelCapabilitiesProfile(
                reasoning=True,
                coding=False,
                planning=True,
                tool_calling=True,
                vision=False,
                latency_tier="fast",
            ),
            min_ram_mb=1024.0,
        )
    )
    reg.register_model(
        ModelDescriptor(
            model_id="test/deep-reasoner",
            display_name="Deep Reasoner 32B",
            engine_type="ollama",
            provider_name="ollama_local",
            capabilities=ModelCapabilitiesProfile(
                reasoning=True,
                coding=True,
                planning=True,
                tool_calling=True,
                vision=False,
                latency_tier="deep",
            ),
            min_ram_mb=2048.0,
        )
    )

    router = ModelRouter(reg, hub)

    # Route fast
    fast_dec = router.route_task(TaskRequirements(preferred_latency="fast", requires_tools=True))
    assert fast_dec.selected_model_id == "test/fast-mini"
    assert not fast_dec.fallback_used

    # Route deep reasoning/coding
    deep_dec = router.route_task(TaskRequirements(requires_coding=True, preferred_latency="deep"))
    assert deep_dec.selected_model_id == "test/deep-reasoner"

    # Route impossible requirement -> fallback to deterministic
    impossible_dec = router.route_task(TaskRequirements(requires_vision=True))
    assert impossible_dec.fallback_used is True
    assert impossible_dec.selected_model_id == "deterministic-local-v1"


@pytest.mark.asyncio
async def test_engine_discovery_handles_offline_gracefully():
    reg = ModelRegistry()
    # Point to invalid port to test timeout/offline resiliency
    disc = EngineDiscovery(
        reg,
        ollama_host="http://localhost:59999",
        llamacpp_host="http://localhost:59998",
        lmstudio_host="http://localhost:59997",
        vllm_host="http://localhost:59996",
        probe_timeout_seconds=0.1,
    )
    res = await disc.discover_all(force_refresh=True)
    assert res["ollama"].available is False
    assert res["llamacpp"].available is False
    # Registry still holds bedrock deterministic model
    assert reg.get_model("deterministic-local-v1") is not None


@pytest.mark.asyncio
async def test_model_manager_routing_and_generation():
    manager = ModelManager(default_provider="deterministic")
    req = ModelRequest(
        messages=[ChatMessage(role=ModelRole.USER, content="ping")],
    )
    # Generate with explicit requirements
    resp = await manager.generate(
        req,
        requirements=TaskRequirements(requires_tools=True, preferred_latency="fast"),
    )
    assert resp.content != ""
    assert resp.model_name != ""

    status = manager.get_system_model_status()
    assert "active_provider" in status
    assert "device" in status
    assert "registered_models_count" in status
    assert status["registered_models_count"] >= 1


def test_wake_word_detector():
    detector = WakeWordDetector(WakeWordConfig(enabled=True, wake_words=["jarvis"]))

    res1 = detector.evaluate("Jarvis open Notepad")
    assert res1.detected is True
    assert res1.cleaned_command == "open Notepad"

    res2 = detector.evaluate("Hey Jarvis, check weather")
    # "Hey Jarvis" isn't in default list unless added or config updated
    detector.config.wake_words.append("hey jarvis")
    res3 = detector.evaluate("Hey Jarvis, check weather")
    assert res3.detected is True
    assert res3.cleaned_command == "check weather"

    res4 = detector.evaluate("Just regular speech without wake word")
    assert res4.detected is False
    assert res4.cleaned_command == "Just regular speech without wake word"


def test_voice_interruption_controller():
    ctrl = VoiceInterruptionController()
    assert not ctrl.is_speaking
    assert ctrl.interrupt() is False

    ctrl.start_speaking("speech-123")
    assert ctrl.is_speaking is True
    assert ctrl.interrupt() is True
    assert ctrl.is_speaking is False
