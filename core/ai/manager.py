"""Model manager coordinating discovery, switching, health, and task-aware model routing."""

from __future__ import annotations

import logging
from typing import Any

from core.ai.discovery import EngineDiscovery
from core.ai.local_provider import DeterministicLocalProvider, LocalModelProvider
from core.ai.model_registry import ModelDescriptor, ModelRegistry
from core.ai.model_router import ModelRouter, RoutingDecision, TaskRequirements
from core.ai.provider import BaseModelProvider
from core.devices.device_hub import DeviceCapability, DeviceHub
from core.models.ai import ModelCapabilities, ModelRequest, ModelResponse, ModelRuntimeInfo

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages AI inference providers, discovery, active selection, and health diagnostics."""

    def __init__(
        self,
        default_provider: str = "deterministic",
        device_hub: DeviceHub | None = None,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        self._providers: dict[str, BaseModelProvider] = {}
        self._active_provider_name: str = default_provider

        # Subsystems
        self._device_hub = device_hub or DeviceHub()
        self._registry = model_registry or ModelRegistry()
        self._discovery = EngineDiscovery(self._registry)
        self._router = ModelRouter(self._registry, self._device_hub)

        # Register standard base providers
        self.register_provider("deterministic", DeterministicLocalProvider())
        self.register_provider("ollama_local", LocalModelProvider())

        if default_provider in self._providers:
            self._active_provider_name = default_provider
        else:
            self._active_provider_name = "deterministic"

        self._last_routing_decision: RoutingDecision | None = None

    @property
    def device_hub(self) -> DeviceHub:
        return self._device_hub

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    @property
    def discovery(self) -> EngineDiscovery:
        return self._discovery

    @property
    def router(self) -> ModelRouter:
        return self._router

    def register_provider(self, name: str, provider: BaseModelProvider) -> None:
        """Register a model provider."""
        self._providers[name] = provider
        logger.info("Registered model provider '%s'", name)

    def set_active_provider(self, name: str) -> None:
        """Switch active provider."""
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not found. Available: {list(self._providers.keys())}")
        self._active_provider_name = name
        logger.info("Active model provider switched to '%s'", name)

    def get_active_provider(self) -> BaseModelProvider:
        """Retrieve active model provider."""
        return self._providers[self._active_provider_name]

    def get_active_provider_name(self) -> str:
        """Return name of active provider."""
        return self._active_provider_name

    def list_providers(self) -> list[ModelRuntimeInfo]:
        """List runtime status of all registered providers."""
        return [provider.get_runtime_info() for provider in self._providers.values()]

    def get_active_info(self) -> ModelRuntimeInfo:
        """Get runtime info of the active provider."""
        return self.get_active_provider().get_runtime_info()

    def get_active_capabilities(self) -> ModelCapabilities:
        """Get capabilities of the active provider."""
        return self.get_active_provider().get_capabilities()

    async def discover_engines(self, force_refresh: bool = False) -> dict[str, Any]:
        """Run engine discovery and register all newly discovered models."""
        results = await self._discovery.discover_all(force_refresh=force_refresh)
        # If Ollama has models and ollama_local provider exists, configure it and promote as active
        ollama_res = results.get("ollama")
        if ollama_res and ollama_res.available and ollama_res.models_found:
            ollama_prov = self._providers.get("ollama_local")
            if isinstance(ollama_prov, LocalModelProvider):
                # Prefer a fast, capable chat model (avoid embedding-only and very large models)
                all_models = ollama_res.models_found
                # Filter out embedding-only models
                chat_models = [
                    m for m in all_models
                    if not any(embed in m.lower() for embed in ("embed", "bge", "nomic"))
                ]
                # Prefer small/fast models using exact size token matching
                # Extract ':Xb' token and check against known fast sizes
                import re as _re
                _FAST_SIZES = frozenset({
                    "0.5b", "1b", "1.5b", "1.7b", "2b", "3b", "3.8b",
                    "4b", "5b", "6b", "7b", "8b",
                })

                def _is_fast_model(model_name: str) -> bool:
                    m = _re.search(r":(\d+(?:\.\d+)?)b", model_name, _re.IGNORECASE)
                    return bool(m) and m.group(1).lower() + "b" in _FAST_SIZES

                fast_models = [m for m in chat_models if _is_fast_model(m)]
                # Final selection: fast model first, then any chat model, else first available
                preferred = (fast_models or chat_models or all_models)[0]
                ollama_prov.model_name = preferred
                # Promote Ollama as active provider
                self._active_provider_name = "ollama_local"
                logger.info(
                    "Auto-promoted ollama_local provider with model '%s' as active provider",
                    preferred,
                )
        return self._discovery.get_discovery_summary()

    def route_task(self, requirements: TaskRequirements) -> RoutingDecision:
        """Route task to best available local model."""
        decision = self._router.route_task(requirements)
        self._last_routing_decision = decision
        return decision

    async def generate(
        self,
        request: ModelRequest,
        requirements: TaskRequirements | None = None,
    ) -> ModelResponse:
        """Forward generation to routed provider or fallback provider."""
        provider_to_use = self.get_active_provider()

        if requirements is not None:
            decision = self.route_task(requirements)
            provider_name = decision.provider_name
            if provider_name in self._providers:
                target_prov = self._providers[provider_name]
                # If target is LocalModelProvider and an ollama model was routed
                if isinstance(target_prov, LocalModelProvider) and decision.selected_model_id.startswith("ollama/"):
                    actual_model_name = decision.selected_model_id.split("/", 1)[1]
                    target_prov.model_name = actual_model_name
                provider_to_use = target_prov
            else:
                provider_to_use = self._providers.get("deterministic", provider_to_use)

        try:
            return await provider_to_use.generate(request)
        except Exception as exc:
            logger.warning("Generation with provider failed (%s), falling back to deterministic: %s", provider_to_use, exc)
            fallback_prov = self._providers.get("deterministic")
            if fallback_prov and fallback_prov != provider_to_use:
                return await fallback_prov.generate(request)
            raise

    async def check_health(self) -> dict[str, bool]:
        """Health check for all providers."""
        health = {}
        for name, provider in self._providers.items():
            try:
                health[name] = await provider.check_health()
            except Exception:
                health[name] = False
        return health

    def get_system_model_status(self) -> dict[str, Any]:
        """Diagnostic state for UI telemetry and REST diagnostics."""
        device = self._device_hub.get_device_capability()
        active_info = self.get_active_info()
        return {
            "active_provider": self._active_provider_name,
            "active_model_id": active_info.model_id,
            "active_engine": active_info.provider_type,
            "device": {
                "device_id": device.device_id,
                "os": f"{device.os_type} {device.architecture}",
                "cpu": device.cpu_model,
                "cores": device.cpu_cores_logical,
                "ram_total_mb": device.ram_total_mb,
                "ram_available_mb": device.ram_available_mb,
                "gpus": [g.model_dump() for g in device.gpus],
            },
            "discovered_engines": self._discovery.get_discovery_summary(),
            "registered_models_count": len(self._registry.list_models(only_available=True)),
            "last_routing_decision": self._last_routing_decision.model_dump() if self._last_routing_decision else None,
        }
