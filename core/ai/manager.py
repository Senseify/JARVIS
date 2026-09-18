"""Model manager coordinating discovery, switching, and health of model providers."""

import logging
from core.ai.local_provider import DeterministicLocalProvider, LocalModelProvider
from core.ai.provider import BaseModelProvider
from core.models.ai import ModelCapabilities, ModelRequest, ModelResponse, ModelRuntimeInfo

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages AI inference providers, discovery, active selection, and health diagnostics."""

    def __init__(self, default_provider: str = "deterministic") -> None:
        self._providers: dict[str, BaseModelProvider] = {}
        self._active_provider_name: str = default_provider

        # Register standard providers
        self.register_provider("deterministic", DeterministicLocalProvider())
        self.register_provider("ollama_local", LocalModelProvider())

        if default_provider in self._providers:
            self._active_provider_name = default_provider
        else:
            self._active_provider_name = "deterministic"

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

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Forward generation to active provider."""
        return await self.get_active_provider().generate(request)

    async def check_health(self) -> dict[str, bool]:
        """Health check for all providers."""
        health = {}
        for name, provider in self._providers.items():
            try:
                health[name] = await provider.check_health()
            except Exception:
                health[name] = False
        return health
