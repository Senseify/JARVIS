"""Models and data structures for vision, OCR, UI element detection, and screen understanding."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator

from windows_agent.observation.models import ScreenState


class BoundingBox(BaseModel):
    """Screen-space bounding rectangle for visual or UI elements."""

    model_config = ConfigDict(extra="forbid")

    left: int = Field(..., ge=0, description="Left X screen coordinate")
    top: int = Field(..., ge=0, description="Top Y screen coordinate")
    width: int = Field(..., gt=0, description="Width of the bounding box")
    height: int = Field(..., gt=0, description="Height of the bounding box")


class Point(BaseModel):
    """2D screen coordinate point."""

    model_config = ConfigDict(extra="forbid")

    x: int = Field(..., ge=0, description="X coordinate")
    y: int = Field(..., ge=0, description="Y coordinate")


class TextRegion(BaseModel):
    """Structured text snippet extracted via OCR."""

    model_config = ConfigDict(extra="ignore")

    text: str = Field(..., description="Recognized text string")
    bounding_box: Optional[BoundingBox] = Field(default=None, description="Bounding rectangle of the text")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    observation_id: str = Field(..., description="Observation identifier this text region was extracted from")


class UIElement(BaseModel):
    """Structured representation of a detected native desktop UI control."""

    model_config = ConfigDict(extra="ignore")

    element_id: str = Field(default_factory=lambda: str(uuid4()), description="Identifier or HWND reference")
    element_type: str = Field(..., description="Control type (e.g. button, text_field, checkbox, window)")
    name: str = Field(default="", description="Label, title, or accessible name")
    bounding_box: Optional[BoundingBox] = Field(default=None, description="Bounding rectangle in screen coordinates")
    center_point: Optional[Point] = Field(default=None, description="Calculated center coordinate for targeting")
    is_enabled: bool = Field(default=True, description="Whether control is enabled for interaction")
    is_visible: bool = Field(default=True, description="Whether control is currently visible on screen")
    is_focused: bool = Field(default=False, description="Whether control currently has keyboard focus")
    interaction_capabilities: List[str] = Field(
        default_factory=list,
        description="Supported actions (e.g. ['click'], ['type'], ['focus'])",
    )

    @model_validator(mode="after")
    def compute_center_point(self) -> "UIElement":
        """Automatically derive center coordinates from bounding box if not explicitly set."""
        if self.bounding_box and self.center_point is None:
            cx = self.bounding_box.left + (self.bounding_box.width // 2)
            cy = self.bounding_box.top + (self.bounding_box.height // 2)
            self.center_point = Point(x=cx, y=cy)
        return self


class ScreenUnderstanding(BaseModel):
    """Comprehensive screen understanding model combining observation, OCR, and UI elements."""

    model_config = ConfigDict(extra="ignore")

    observation_id: str = Field(..., description="Associated observation ID")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    screen_state: ScreenState = Field(..., description="Underlying screen state metadata")
    active_window: Optional[Dict[str, Any]] = Field(default=None, description="Foreground active window metadata")
    text_regions: List[TextRegion] = Field(default_factory=list, description="Extracted OCR text regions")
    ui_elements: List[UIElement] = Field(default_factory=list, description="Detected native UI controls")


class ScreenOCRParams(BaseModel):
    """Validation schema for screen.ocr capability."""

    model_config = ConfigDict(extra="forbid")

    observation_id: Optional[str] = Field(
        default=None,
        description="Observation ID to analyze. If omitted, captures a new observation.",
    )


class ScreenUIElementsParams(BaseModel):
    """Validation schema for screen.ui_elements capability."""

    model_config = ConfigDict(extra="forbid")

    observation_id: Optional[str] = Field(
        default=None,
        description="Observation ID to analyze. If omitted, captures a new observation.",
    )
    window_handle: Optional[int] = Field(
        default=None,
        description="Optional window HWND to restrict UI element search.",
    )


class ScreenUnderstandParams(BaseModel):
    """Validation schema for screen.understand capability."""

    model_config = ConfigDict(extra="forbid")

    observation_id: Optional[str] = Field(
        default=None,
        description="Observation ID to analyze. If omitted, captures a new observation.",
    )
