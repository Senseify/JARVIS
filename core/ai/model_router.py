"""Task-aware Model Router for JARVIS OS.

Dynamically selects the optimal available local model based on task complexity,
required capabilities, device hardware constraints (RAM/VRAM), and latency tier,
with zero silent cloud leakage.
"""

from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, Field

from core.ai.model_registry import ModelDescriptor, ModelRegistry
from core.devices.device_hub import DeviceHub

logger = logging.getLogger(__name__)


class TaskRequirements(BaseModel):
    """Specification of capabilities required for an inference task."""

    requires_tools: bool = True
    requires_vision: bool = False
    requires_coding: bool = False
    requires_reasoning: bool = True
    requires_embeddings: bool = False
    min_context_window: int = 2048
    preferred_latency: str = "balanced"  # "fast", "balanced", "deep"
    task_hint: str = ""  # e.g. "code_generation", "screen_ocr", "quick_greeting"


class RoutingDecision(BaseModel):
    """Result and audit log of a model routing evaluation."""

    selected_model_id: str
    display_name: str
    provider_name: str
    engine_type: str
    routing_reason: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    candidate_count: int = 0
    estimated_ram_mb: float = 0.0


class ModelRouter:
    """Intelligently routes inference requests to the best available local model."""

    def __init__(self, registry: ModelRegistry, device_hub: DeviceHub) -> None:
        self.registry = registry
        self.device_hub = device_hub

    def route_task(self, requirements: TaskRequirements) -> RoutingDecision:
        """Evaluate registered models against requirements and device hardware."""
        device = self.device_hub.get_device_capability()
        avail_ram = device.ram_available_mb if device.ram_available_mb > 0 else 8192.0
        candidates = self.registry.list_models(only_available=True)

        # 1. Filter out models requiring more RAM than currently available
        viable: list[tuple[ModelDescriptor, float]] = []
        for m in candidates:
            caps = m.capabilities

            # Exclude models exceeding memory (allow deterministic fallback regardless)
            if m.engine_type != "deterministic" and m.min_ram_mb > (avail_ram * 1.5):
                continue

            # Hard capability filters
            if requirements.requires_vision and not caps.vision:
                continue
            if requirements.requires_tools and not caps.tool_calling:
                continue
            if requirements.requires_embeddings and not caps.embeddings:
                continue
            if not requirements.requires_embeddings and caps.embeddings:
                # Do not route general text reasoning to embedding-only models
                continue
            if caps.context_window < requirements.min_context_window:
                continue

            # Compute match score
            score = 10.0

            # Specialization bonuses
            name_lower = m.model_id.lower()
            if requirements.requires_coding:
                if caps.coding or any(c in name_lower for c in ("code", "deepseek", "starcoder")):
                    score += 25.0
            if requirements.requires_reasoning:
                if any(r in name_lower for r in ("r1", "reason", "qwen3.5", "llama3")):
                    score += 20.0
                if any(s in name_lower for s in ("9b", "14b", "27b", "32b")):
                    score += 10.0

            # Latency preference match
            if requirements.preferred_latency == "fast":
                if caps.latency_tier == "fast" or any(s in name_lower for s in ("0.5b", "1.5b", "1b", "2b")):
                    score += 40.0
                elif caps.latency_tier == "deep":
                    score -= 30.0
            elif requirements.preferred_latency == "deep":
                if caps.latency_tier == "deep" or any(s in name_lower for s in ("14b", "27b", "32b", "70b")):
                    score += 35.0
                elif caps.latency_tier == "fast":
                    score -= 15.0

            # Prioritize real local engines over pure rule-based deterministic fallback when available
            if m.engine_type != "deterministic":
                score += 20.0

            viable.append((m, score))

        if viable:
            viable.sort(key=lambda x: x[1], reverse=True)
            chosen, score = viable[0]
            reason = (
                f"Matched requirements (tools={requirements.requires_tools}, "
                f"vision={requirements.requires_vision}, coding={requirements.requires_coding}, "
                f"latency={requirements.preferred_latency}). Candidate score: {score:.1f} on {chosen.engine_type}."
            )
            return RoutingDecision(
                selected_model_id=chosen.model_id,
                display_name=chosen.display_name,
                provider_name=chosen.provider_name,
                engine_type=chosen.engine_type,
                routing_reason=reason,
                fallback_used=False,
                candidate_count=len(viable),
                estimated_ram_mb=chosen.min_ram_mb,
            )

        # 2. Graceful deterministic local fallback
        fallback = self.registry.get_model("deterministic-local-v1")
        return RoutingDecision(
            selected_model_id="deterministic-local-v1",
            display_name="JARVIS Deterministic Reasoner",
            provider_name="deterministic",
            engine_type="deterministic",
            routing_reason="No external local model met strict requirements or memory constraints. Selected local deterministic engine.",
            fallback_used=True,
            fallback_reason="No compatible external engine model found matching requirements.",
            candidate_count=0,
            estimated_ram_mb=256.0,
        )
