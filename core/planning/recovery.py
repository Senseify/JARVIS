"""Dedicated recovery engine for automated fault classification, screen reinspection, and safe retry."""

import logging
from typing import Any
from core.constants import EventType, OrbState
from core.events.bus import EventBus
from core.models.events import AgentEvent
from core.models.planning import FailureClassification, PlanStep, StepStatus

logger = logging.getLogger(__name__)


class RecoveryEngine:
    """Manages failure classification and safe bounded recovery strategies."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def classify_failure(self, error: str | None, verification_details: dict[str, Any] | None = None) -> FailureClassification:
        """Classify failure mode from error string and verification receipts."""
        text = ((error or "") + " " + str(verification_details or "")).lower()

        if "window not found" in text or "window_not_found" in text or "no matching window" in text:
            return FailureClassification.WINDOW_NOT_FOUND
        if "element not found" in text or "not visible" in text or "could not locate" in text:
            return FailureClassification.ELEMENT_NOT_FOUND
        if "verification failed" in text or "text mismatch" in text or "unverified" in text:
            return FailureClassification.VERIFICATION_FAILED
        if "timed out" in text or "timeout" in text:
            return FailureClassification.TIMEOUT
        if "policy" in text or "blocked" in text or "not allowed" in text:
            return FailureClassification.POLICY_BLOCKED
        if "device offline" in text or "disconnected" in text:
            return FailureClassification.DEVICE_UNAVAILABLE
        if "tool error" in text:
            return FailureClassification.TOOL_ERROR

        return FailureClassification.UNKNOWN

    async def attempt_recovery(
        self,
        step: PlanStep,
        plan_id: str,
        classification: FailureClassification,
    ) -> bool:
        """Evaluate if step can safely be recovered and increment retry count.

        Returns True if a retry should be attempted, False if recovery exhausted.
        """
        if step.retry_count >= step.max_retries:
            logger.warning(
                "Plan %s Step %s exceeded max retries (%d/%d). Aborting recovery.",
                plan_id,
                step.step_id,
                step.retry_count,
                step.max_retries,
            )
            step.status = StepStatus.FAILED
            return False

        step.retry_count += 1
        step.status = StepStatus.RECOVERING

        logger.info(
            "Attempting recovery for step '%s' (attempt %d/%d, reason: %s)",
            step.name,
            step.retry_count,
            step.max_retries,
            classification.value,
        )

        if self.event_bus:
            await self.event_bus.publish(
                AgentEvent(
                    event_type=EventType.PLAN_RECOVERING,
                    payload={
                        "plan_id": plan_id,
                        "step_id": step.step_id,
                        "retry_count": step.retry_count,
                        "max_retries": step.max_retries,
                        "classification": classification.value,
                    },
                )
            )
            await self.event_bus.publish(
                AgentEvent(
                    event_type=EventType.ORB_STATE_CHANGED,
                    payload={"state": OrbState.RECOVERING, "detail": f"Recovering step {step.name}"},
                )
            )

        return True
