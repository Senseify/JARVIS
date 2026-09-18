"""Abstract base provider for model inference in JARVIS OS."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from core.models.ai import ModelCapabilities, ModelRequest, ModelResponse, ModelRuntimeInfo


class BaseModelProvider(ABC):
    """Abstract contract for all AI inference providers (local and optional cloud)."""

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Execute a structured completion or tool-calling request."""
        pass

    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """Stream response tokens if supported. Default falls back to full generation."""
        response = await self.generate(request)
        yield response.content

    @abstractmethod
    def get_capabilities(self) -> ModelCapabilities:
        """Return provider capabilities and constraints."""
        pass

    @abstractmethod
    async def check_health(self) -> bool:
        """Check if provider backend is reachable and ready."""
        pass

    @abstractmethod
    def get_runtime_info(self) -> ModelRuntimeInfo:
        """Return diagnostic runtime state."""
        pass
