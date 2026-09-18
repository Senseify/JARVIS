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

    def verify_text_present(
        self,
        expected_text: str,
        text_regions: List[Any],
        case_sensitive: bool = False,
    ) -> VerificationResult:
        """Verify that expected text is detected in OCR text regions."""
        target = expected_text if case_sensitive else expected_text.strip().lower()

        matching = []
        for region in text_regions:
            r_text = getattr(region, "text", "") if hasattr(region, "text") else region.get("text", "")
            compare_text = r_text if case_sensitive else r_text.strip().lower()
            if target in compare_text:
                matching.append(r_text)

        passed = len(matching) > 0
        failure_reason = None if passed else f"Expected text '{expected_text}' not found in {len(text_regions)} OCR text regions."

        return VerificationResult(
            check_type="ocr_text_present",
            expected_condition=f"OCR text contains '{expected_text}'",
            observed_state=matching,
            passed=passed,
            failure_reason=failure_reason,
        )

    def verify_text_absent(
        self,
        expected_text: str,
        text_regions: List[Any],
        case_sensitive: bool = False,
    ) -> VerificationResult:
        """Verify that specific text is absent from OCR text regions."""
        target = expected_text if case_sensitive else expected_text.strip().lower()

        matching = []
        for region in text_regions:
            r_text = getattr(region, "text", "") if hasattr(region, "text") else region.get("text", "")
            compare_text = r_text if case_sensitive else r_text.strip().lower()
            if target in compare_text:
                matching.append(r_text)

        passed = len(matching) == 0
        failure_reason = None if passed else f"Text '{expected_text}' is unexpectedly present in OCR text regions: {matching}."

        return VerificationResult(
            check_type="ocr_text_absent",
            expected_condition=f"OCR text does not contain '{expected_text}'",
            observed_state=matching,
            passed=passed,
            failure_reason=failure_reason,
        )

    def verify_ui_element(
        self,
        ui_elements: List[Any],
        name: Optional[str] = None,
        element_type: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        is_visible: Optional[bool] = None,
    ) -> VerificationResult:
        """Verify native UI element presence and state against expected attributes."""
        matching = []
        for el in ui_elements:
            el_name = getattr(el, "name", "") if hasattr(el, "name") else el.get("name", "")
            el_type = getattr(el, "element_type", "") if hasattr(el, "element_type") else el.get("element_type", "")
            el_enabled = getattr(el, "is_enabled", True) if hasattr(el, "is_enabled") else el.get("is_enabled", True)
            el_visible = getattr(el, "is_visible", True) if hasattr(el, "is_visible") else el.get("is_visible", True)

            if name and name.strip().lower() not in el_name.strip().lower():
                continue
            if element_type and element_type.strip().lower() != el_type.strip().lower():
                continue
            if is_enabled is not None and el_enabled != is_enabled:
                continue
            if is_visible is not None and el_visible != is_visible:
                continue

            matching.append({
                "id": getattr(el, "element_id", None) or (el.get("element_id") if isinstance(el, dict) else None),
                "name": el_name,
                "type": el_type,
                "enabled": el_enabled,
                "visible": el_visible,
            })

        passed = len(matching) > 0
        expected_desc = f"name='{name}'" if name else ""
        if element_type:
            expected_desc += f", type='{element_type}'"
        if is_enabled is not None:
            expected_desc += f", enabled={is_enabled}"
        if is_visible is not None:
            expected_desc += f", visible={is_visible}"

        failure_reason = None if passed else f"No UI element matching ({expected_desc.strip(', ')}) found in {len(ui_elements)} detected controls."

        return VerificationResult(
            check_type="ui_element",
            expected_condition=f"UI element matching ({expected_desc.strip(', ')})",
            observed_state=matching,
            passed=passed,
            failure_reason=failure_reason,
        )

    def verify_condition(
        self,
        condition: str,
        expected_value: Any,
        screen_state: Optional[ScreenState] = None,
        window_list: Optional[List[Dict[str, Any]]] = None,
        text_regions: Optional[List[Any]] = None,
        ui_elements: Optional[List[Any]] = None,
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

        if cond_lower in ("text_present", "ocr_text_present", "text_exists"):
            if text_regions is None:
                raise ValueError("Text regions required for text_present check.")
            return self.verify_text_present(str(expected_value), text_regions)

        if cond_lower in ("text_absent", "ocr_text_absent", "text_not_present"):
            if text_regions is None:
                raise ValueError("Text regions required for text_absent check.")
            return self.verify_text_absent(str(expected_value), text_regions)

        if cond_lower in ("ui_element_exists", "ui_element", "ui_element_present"):
            if ui_elements is None:
                raise ValueError("UI elements required for ui_element check.")
            if isinstance(expected_value, dict):
                return self.verify_ui_element(
                    ui_elements,
                    name=expected_value.get("name"),
                    element_type=expected_value.get("type"),
                    is_enabled=expected_value.get("enabled"),
                    is_visible=expected_value.get("visible"),
                )
            return self.verify_ui_element(ui_elements, name=str(expected_value))

        if cond_lower in ("ui_element_visible",):
            if ui_elements is None:
                raise ValueError("UI elements required for ui_element_visible check.")
            name = expected_value.get("name") if isinstance(expected_value, dict) else str(expected_value)
            el_type = expected_value.get("type") if isinstance(expected_value, dict) else None
            return self.verify_ui_element(ui_elements, name=name, element_type=el_type, is_visible=True)

        if cond_lower in ("ui_element_enabled",):
            if ui_elements is None:
                raise ValueError("UI elements required for ui_element_enabled check.")
            name = expected_value.get("name") if isinstance(expected_value, dict) else str(expected_value)
            el_type = expected_value.get("type") if isinstance(expected_value, dict) else None
            return self.verify_ui_element(ui_elements, name=name, element_type=el_type, is_enabled=True)

        raise ValueError(f"Unknown verification condition: '{condition}'")
