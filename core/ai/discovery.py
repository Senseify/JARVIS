"""Inference Engine Discovery Layer for JARVIS OS.

Probes locally running inference engines (Ollama, llama.cpp, LM Studio, vLLM, MLX)
via lightweight HTTP health and model queries with tight timeouts (0.5s) to avoid
blocking or stalling. Never downloads large weights automatically.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
from typing import Any
import httpx

from core.ai.model_registry import ModelCapabilitiesProfile, ModelDescriptor, ModelRegistry

logger = logging.getLogger(__name__)


class EngineDiscoveryResult(BaseModel := object):
    """Result of an engine discovery probe."""

    def __init__(self, engine_name: str, available: bool, endpoint: str, models_found: list[str], latency_ms: float = 0.0) -> None:
        self.engine_name = engine_name
        self.available = available
        self.endpoint = endpoint
        self.models_found = models_found
        self.latency_ms = latency_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "available": self.available,
            "endpoint": self.endpoint,
            "models_found": self.models_found,
            "latency_ms": self.latency_ms,
        }


class EngineDiscovery:
    """Discovers and catalogs local inference engines."""

    def __init__(
        self,
        registry: ModelRegistry,
        ollama_host: str = "http://localhost:11434",
        llamacpp_host: str = "http://localhost:8080",
        lmstudio_host: str = "http://localhost:1234",
        vllm_host: str = "http://localhost:8000",
        probe_timeout_seconds: float = 0.5,
    ) -> None:
        self.registry = registry
        self.ollama_host = os.environ.get("JARVIS_OLLAMA_HOST", ollama_host)
        self.llamacpp_host = os.environ.get("JARVIS_LLAMACPP_HOST", llamacpp_host)
        self.lmstudio_host = os.environ.get("JARVIS_LMSTUDIO_HOST", lmstudio_host)
        self.vllm_host = os.environ.get("JARVIS_VLLM_HOST", vllm_host)
        self.timeout = probe_timeout_seconds
        self._last_discovery_time: float = 0.0
        self._engine_states: dict[str, EngineDiscoveryResult] = {}

    async def probe_ollama(self, client: httpx.AsyncClient) -> EngineDiscoveryResult:
        """Probe Ollama server for installed models."""
        t0 = time.time()
        try:
            resp = await client.get(f"{self.ollama_host}/api/tags", timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                found = []
                self.registry.clear_engine_models("ollama")
                for item in models:
                    name = item.get("name", "")
                    if not name:
                        continue
                    found.append(name)
                    # Infer capabilities from name heuristics
                    is_vision = any(v in name.lower() for v in ("vision", "llava", "moondream", "minicpm-v"))
                    is_coder = any(c in name.lower() for c in ("code", "coder", "deepseek-coder", "starcoder"))
                    caps = ModelCapabilitiesProfile(
                        reasoning=True,
                        coding=is_coder,
                        planning=True,
                        tool_calling=not is_vision,
                        vision=is_vision,
                        embeddings="embed" in name.lower(),
                        context_window=32768 if "qwen" in name.lower() or "llama" in name.lower() else 8192,
                        latency_tier="fast" if any(s in name for s in ("0.5b", "1.5b", "3b")) else "balanced",
                    )
                    size_bytes = item.get("size", 0)
                    param_size = "unknown"
                    for tag in ("0.5b", "1.5b", "3b", "7b", "8b", "14b", "32b", "70b"):
                        if tag in name.lower():
                            param_size = tag.upper()
                            break

                    self.registry.register_model(
                        ModelDescriptor(
                            model_id=f"ollama/{name}",
                            display_name=f"Ollama: {name}",
                            engine_type="ollama",
                            provider_name="ollama_local",
                            capabilities=caps,
                            parameter_size=param_size,
                            size_bytes=size_bytes,
                            min_ram_mb=4096.0 if "7b" in name.lower() else 2048.0,
                            status="available",
                            is_local=True,
                        )
                    )
                latency = round((time.time() - t0) * 1000, 1)
                return EngineDiscoveryResult("ollama", True, self.ollama_host, found, latency)
        except Exception:
            pass
        return EngineDiscoveryResult("ollama", False, self.ollama_host, [], 0.0)

    async def probe_openai_compat(self, client: httpx.AsyncClient, name: str, host: str) -> EngineDiscoveryResult:
        """Probe standard OpenAI-compatible local engines (llama.cpp, LM Studio, vLLM)."""
        t0 = time.time()
        try:
            resp = await client.get(f"{host}/v1/models", timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                found = []
                self.registry.clear_engine_models(name)
                for item in models:
                    mid = item.get("id", "")
                    if not mid:
                        continue
                    found.append(mid)
                    is_vision = "vision" in mid.lower() or "vl" in mid.lower()
                    is_coder = "code" in mid.lower()
                    caps = ModelCapabilitiesProfile(
                        reasoning=True,
                        coding=is_coder,
                        planning=True,
                        tool_calling=True,
                        vision=is_vision,
                        embeddings="embed" in mid.lower(),
                        context_window=16384,
                        latency_tier="fast",
                    )
                    self.registry.register_model(
                        ModelDescriptor(
                            model_id=f"{name}/{mid}",
                            display_name=f"{name.upper()}: {mid}",
                            engine_type=name,
                            provider_name=f"{name}_provider",
                            capabilities=caps,
                            parameter_size="unknown",
                            min_ram_mb=4096.0,
                            status="available",
                            is_local=True,
                        )
                    )
                latency = round((time.time() - t0) * 1000, 1)
                return EngineDiscoveryResult(name, True, host, found, latency)
        except Exception:
            pass
        return EngineDiscoveryResult(name, False, host, [], 0.0)

    def probe_mlx_in_process(self) -> EngineDiscoveryResult:
        """Check for in-process Apple MLX on macOS Apple Silicon."""
        if platform.system().lower() == "darwin" and platform.machine() == "arm64":
            try:
                import mlx.core as mx  # type: ignore[import-not-found]
                return EngineDiscoveryResult("mlx", True, "in-process", ["mlx-metal-engine"], 0.1)
            except ImportError:
                return EngineDiscoveryResult("mlx", False, "in-process", [], 0.0)
        return EngineDiscoveryResult("mlx", False, "in-process", [], 0.0)

    async def discover_all(self, force_refresh: bool = False) -> dict[str, EngineDiscoveryResult]:
        """Probe all engines concurrently with minimal overhead."""
        now = time.time()
        if not force_refresh and self._engine_states and (now - self._last_discovery_time < 15.0):
            return self._engine_states

        async with httpx.AsyncClient() as client:
            tasks = [
                self.probe_ollama(client),
                self.probe_openai_compat(client, "llamacpp", self.llamacpp_host),
                self.probe_openai_compat(client, "lmstudio", self.lmstudio_host),
                # Note: vLLM default host 8000 might collide with our own port, so check if custom
                self.probe_openai_compat(client, "vllm", self.vllm_host if self.vllm_host != "http://localhost:8000" else "http://localhost:8001"),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        states: dict[str, EngineDiscoveryResult] = {}
        for r in results:
            if isinstance(r, EngineDiscoveryResult):
                states[r.engine_name] = r

        # In-process probes
        mlx_res = self.probe_mlx_in_process()
        states["mlx"] = mlx_res

        self._engine_states = states
        self._last_discovery_time = now
        return states

    def get_discovery_summary(self) -> dict[str, Any]:
        """Return diagnostic dictionary of engine discovery states."""
        return {k: v.to_dict() for k, v in self._engine_states.items()}
