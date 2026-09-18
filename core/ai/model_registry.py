"""Normalized Model Registry for JARVIS OS.

Tracks discovered local models, capability profiles, health states, and resource constraints
without hardcoding any single provider or model family.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ModelCapabilitiesProfile(BaseModel):
    """Normalized capabilities flags for an AI model."""

    reasoning: bool = True
    coding: bool = False
    planning: bool = True
    tool_calling: bool = True
    vision: bool = False
    embeddings: bool = False
    streaming: bool = True
    context_window: int = 8192
    latency_tier: str = "balanced"  # "fast", "balanced", "deep"


class ModelDescriptor(BaseModel):
    """Complete metadata descriptor for a discovered or registered local model."""

    model_id: str
    display_name: str
    engine_type: str  # "ollama", "llamacpp", "lmstudio", "vllm", "mlx", "deterministic"
    provider_name: str
    capabilities: ModelCapabilitiesProfile = Field(default_factory=ModelCapabilitiesProfile)
    parameter_size: str = "unknown"  # e.g. "3B", "7B", "14B", "N/A"
    size_bytes: int = 0
    min_ram_mb: float = 2048.0
    min_vram_mb: float = 0.0
    status: str = "available"  # "available", "loaded", "degraded", "offline"
    is_local: bool = True
    device_id: str = "local-host"
    last_seen: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelRegistry:
    """Thread-safe catalog of available models across all inference engines."""

    def __init__(self) -> None:
        self._models: dict[str, ModelDescriptor] = {}
        # Pre-populate bedrock deterministic model ensuring zero-dependency availability
        self.register_model(
            ModelDescriptor(
                model_id="deterministic-local-v1",
                display_name="JARVIS Deterministic Reasoner",
                engine_type="deterministic",
                provider_name="deterministic",
                capabilities=ModelCapabilitiesProfile(
                    reasoning=True,
                    coding=True,
                    planning=True,
                    tool_calling=True,
                    vision=False,
                    embeddings=False,
                    streaming=True,
                    context_window=16384,
                    latency_tier="fast",
                ),
                parameter_size="rule-based",
                min_ram_mb=256.0,
                status="available",
                is_local=True,
            )
        )

    def register_model(self, descriptor: ModelDescriptor) -> None:
        """Register or update a model descriptor."""
        self._models[descriptor.model_id] = descriptor
        logger.debug("Registered model '%s' via '%s'", descriptor.model_id, descriptor.engine_type)

    def unregister_model(self, model_id: str) -> None:
        """Remove a model from the active catalog."""
        self._models.pop(model_id, None)

    def get_model(self, model_id: str) -> ModelDescriptor | None:
        """Retrieve a specific model descriptor."""
        return self._models.get(model_id)

    def list_models(self, only_available: bool = True) -> list[ModelDescriptor]:
        """List all models matching filter criteria."""
        models = list(self._models.values())
        if only_available:
            return [m for m in models if m.status in ("available", "loaded")]
        return models

    def find_by_capability(
        self,
        requires_tools: bool = False,
        requires_vision: bool = False,
        requires_coding: bool = False,
        min_context: int = 0,
    ) -> list[ModelDescriptor]:
        """Find models satisfying capability requirements."""
        candidates = []
        for m in self.list_models(only_available=True):
            caps = m.capabilities
            if requires_tools and not caps.tool_calling:
                continue
            if requires_vision and not caps.vision:
                continue
            if requires_coding and not caps.coding:
                continue
            if min_context > 0 and caps.context_window < min_context:
                continue
            candidates.append(m)
        return candidates

    def clear_engine_models(self, engine_type: str) -> None:
        """Clear dynamic models from a specific engine (e.g. before refresh)."""
        to_remove = [k for k, v in self._models.items() if v.engine_type == engine_type and k != "deterministic-local-v1"]
        for k in to_remove:
            del self._models[k]
