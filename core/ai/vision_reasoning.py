"""Vision-Assisted Computer Reasoning Adapter.

Synthesizes desktop screen state (OCR, UI trees, active window) into structured
context for reasoning. Seamlessly falls back to structured OCR/UI representation
when no multimodal vision model is available.
"""

from typing import Any
from core.models.ai import ModelCapabilities


class VisionReasoningAdapter:
    """Bridges screen observation data to the Reasoning Engine."""

    def __init__(self) -> None:
        pass

    def format_screen_context(
        self,
        active_window: dict[str, Any] | None = None,
        ocr_regions: list[dict[str, Any]] | None = None,
        ui_elements: list[dict[str, Any]] | None = None,
        capabilities: ModelCapabilities | None = None,
    ) -> str:
        """Format desktop observations into an intelligible text prompt for the reasoner."""
        lines = ["[Desktop Screen State]"]

        # Active foreground window
        if active_window:
            title = active_window.get("title", "Unknown")
            app = active_window.get("process_name", active_window.get("app", "Unknown"))
            lines.append(f"- Active Window: '{title}' (Process: {app})")
        else:
            lines.append("- Active Window: None detected or background desktop")

        # UI Elements
        if ui_elements:
            lines.append(f"- Detected Interactive Elements ({len(ui_elements)} total):")
            for elem in ui_elements[:15]:  # limit to top 15 elements to avoid token bloat
                name = elem.get("name", "unnamed")
                ctrl = elem.get("control_type", "element")
                bbox = elem.get("bounding_box", {})
                lines.append(f"  • {ctrl.capitalize()} '{name}' at ({bbox.get('x', 0)}, {bbox.get('y', 0)})")
        else:
            lines.append("- Detected Interactive Elements: None")

        # Visible text / OCR regions
        if ocr_regions:
            lines.append(f"- Visible Screen Text ({len(ocr_regions)} regions):")
            for region in ocr_regions[:20]:
                text = region.get("text", "").strip()
                if text:
                    lines.append(f"  • \"{text}\"")
        else:
            lines.append("- Visible Screen Text: None detected")

        if capabilities and capabilities.supports_vision:
            lines.append("- Visual Reasoning Mode: Native Multimodal Vision Active")
        else:
            lines.append("- Visual Reasoning Mode: Structured OCR & UI Accessibility Fallback (No vision weights required)")

        return "\n".join(lines)
