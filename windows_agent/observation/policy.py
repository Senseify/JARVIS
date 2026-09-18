"""Adaptive observation policy governing when screen captures are authorized."""

from enum import Enum


class ObservationTrigger(str, Enum):
    """Triggers determining whether screen observation should take place."""

    IDLE = "idle"
    BEFORE_ACTION = "before_action"
    AFTER_ACTION = "after_action"
    VERIFYING = "verifying"
    ERROR = "error"
    RECOVERING = "recovering"


class AdaptiveObservationPolicy:
    """Policy engine deciding whether to trigger a screen capture for a given lifecycle state."""

    def __init__(self, capture_on_error: bool = True):
        self.capture_on_error = capture_on_error

    def should_observe(
        self,
        trigger: ObservationTrigger,
        require_pre_observe: bool = False,
        require_verification: bool = False,
    ) -> bool:
        """Evaluate observation trigger against policy constraints."""
        if trigger == ObservationTrigger.IDLE:
            # Idle: strictly zero continuous capture
            return False

        if trigger == ObservationTrigger.BEFORE_ACTION:
            return require_pre_observe

        if trigger == ObservationTrigger.AFTER_ACTION:
            return require_verification

        if trigger == ObservationTrigger.VERIFYING:
            return True

        if trigger == ObservationTrigger.ERROR:
            return self.capture_on_error

        if trigger == ObservationTrigger.RECOVERING:
            return True

        return False
