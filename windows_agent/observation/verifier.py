"""Deterministic verification engine checking observed screen and window states against expected conditions."""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from windows_agent.observation.models import ScreenState, VerificationResult

logger = logging.getLogger(__name__)


class VerificationEngine:
    """Verifies that an action resulted in the expected system, window, or screen state."""

    def verify_active_window_title(
        self,
        screen_state: ScreenState,
        expected_title: str,
        exact: bool = False,
    ) -> VerificationResult:
        """Verify that the foreground window title matches expected string."""
        active_window = screen_state.active_window
        observed_title = active_window.get("title", "") if active_window else ""

        if exact:
            passed = observed_title.strip().lower() == expected_title.strip().lower()
        else:
            passed = expected_title.strip().lower() in observed_title.strip().lower()

        failure_reason = None if passed else f"Active window title '{observed_title}' does not match expected '{expected_title}'."

        return VerificationResult(
            check_type="active_window_title",
            expected_condition=f"Active window title {'==' if exact else 'contains'} '{expected_title}'",
            observed_state=observed_title,
            passed=passed,
            failure_reason=failure_reason,
        )

    def verify_window_exists(
        self,
        window_list: List[Dict[str, Any]],
        expected_title_substring: str,
    ) -> VerificationResult:
        """Verify that a window containing the expected title exists in the window list."""
        matching = [
            w for w in window_list
            if expected_title_substring.strip().lower() in w.get("title", "").strip().lower()
        ]
        passed = len(matching) > 0
        failure_reason = None if passed else f"No window containing '{expected_title_substring}' found in {len(window_list)} enumerated windows."

        return VerificationResult(
            check_type="window_exists",
            expected_condition=f"Window list contains '{expected_title_substring}'",
            observed_state=[w.get("title") for w in matching],
            passed=passed,
            failure_reason=failure_reason,
        )

    def verify_window_is_visible(
        self,
        window_list: List[Dict[str, Any]],
        expected_title_substring: str,
    ) -> VerificationResult:
        """Verify that a window exists AND is marked visible."""
        matching = [
            w for w in window_list
            if expected_title_substring.strip().lower() in w.get("title", "").strip().lower()
        ]
        if not matching:
            return VerificationResult(
                check_type="window_is_visible",
                expected_condition=f"Visible window containing '{expected_title_substring}'",
                observed_state=[],
                passed=False,
                failure_reason=f"Window '{expected_title_substring}' does not exist.",
            )

        visible_matching = [w for w in matching if w.get("is_visible")]
        passed = len(visible_matching) > 0
        failure_reason = None if passed else f"Window '{expected_title_substring}' exists but is not visible."

        return VerificationResult(
            check_type="window_is_visible",
            expected_condition=f"Window '{expected_title_substring}' is visible",
            observed_state=[w.get("title") for w in visible_matching],
            passed=passed,
            failure_reason=failure_reason,
        )

    def verify_window_disappeared(
        self,
        window_list: List[Dict[str, Any]],
        title_substring: str,
    ) -> VerificationResult:
        """Verify that no window with the specified title exists."""
        matching = [
            w for w in window_list
            if title_substring.strip().lower() in w.get("title", "").strip().lower()
        ]
        passed = len(matching) == 0
        failure_reason = None if passed else f"Window containing '{title_substring}' still exists: {[w.get('title') for w in matching]}."

        return VerificationResult(
            check_type="window_disappeared",
            expected_condition=f"Window '{title_substring}' is closed/absent",
            observed_state=[w.get("title") for w in matching],
            passed=passed,
            failure_reason=failure_reason,
        )

    def verify_screen_dimensions(
        self,
        screen_state: ScreenState,
        min_width: int = 640,
        min_height: int = 480,
    ) -> VerificationResult:
        """Verify that observed screen dimensions are valid."""
        passed = screen_state.width >= min_width and screen_state.height >= min_height
        observed = {"width": screen_state.width, "height": screen_state.height}
        failure_reason = None if passed else f"Screen dimensions {observed} are below minimum ({min_width}x{min_height})."

        return VerificationResult(
            check_type="screen_dimensions",
            expected_condition=f"Width >= {min_width}, Height >= {min_height}",
            observed_state=observed,
            passed=passed,
            failure_reason=failure_reason,
        )

    def verify_condition(
        self,
        condition: str,
        expected_value: Any,
        screen_state: Optional[ScreenState] = None,
        window_list: Optional[List[Dict[str, Any]]] = None,
    ) -> VerificationResult:
        """Dispatch a condition check by name."""
        cond_lower = condition.strip().lower()

        if cond_lower in ("active_window_title", "active_window"):
            if not screen_state:
                raise ValueError("ScreenState required for active_window_title check.")
            return self.verify_active_window_title(screen_state, str(expected_value))

        if cond_lower in ("window_exists", "app_exists", "window_present"):
            if window_list is None:
                raise ValueError("Window list required for window_exists check.")
            return self.verify_window_exists(window_list, str(expected_value))

        if cond_lower in ("window_visible", "window_is_visible"):
            if window_list is None:
                raise ValueError("Window list required for window_visible check.")
            return self.verify_window_is_visible(window_list, str(expected_value))

        if cond_lower in ("window_closed", "window_disappeared"):
            if window_list is None:
                raise ValueError("Window list required for window_disappeared check.")
            return self.verify_window_disappeared(window_list, str(expected_value))

        if cond_lower in ("screen_dimensions", "valid_screen"):
            if not screen_state:
                raise ValueError("ScreenState required for screen_dimensions check.")
            return self.verify_screen_dimensions(screen_state)

        raise ValueError(f"Unknown verification condition: '{condition}'")
