"""Tests for Phase 6A vision models, coordinate mapping, and vision cache."""

import time
import pytest
from pydantic import ValidationError

from windows_agent.observation.models import ScreenState
from windows_agent.vision.cache import VisionCache
from windows_agent.vision.models import (
    BoundingBox,
    Point,
    ScreenOCRParams,
    ScreenUIElementsParams,
    ScreenUnderstandParams,
    ScreenUnderstanding,
    TextRegion,
    UIElement,
)


def test_bounding_box_validation():
    """Verify BoundingBox schema and bounds enforcement."""
    box = BoundingBox(left=10, top=20, width=100, height=50)
    assert box.left == 10
    assert box.top == 20
    assert box.width == 100
    assert box.height == 50

    # Negative coordinates
    with pytest.raises(ValidationError):
        BoundingBox(left=-1, top=0, width=100, height=50)
    with pytest.raises(ValidationError):
        BoundingBox(left=0, top=-5, width=100, height=50)

    # Zero or negative dimensions
    with pytest.raises(ValidationError):
        BoundingBox(left=0, top=0, width=0, height=50)
    with pytest.raises(ValidationError):
        BoundingBox(left=0, top=0, width=100, height=0)

    # Forbidden extra fields
    with pytest.raises(ValidationError):
        BoundingBox(left=0, top=0, width=100, height=50, extra_val=123)


def test_point_validation():
    """Verify Point coordinates schema."""
    pt = Point(x=150, y=300)
    assert pt.x == 150
    assert pt.y == 300

    with pytest.raises(ValidationError):
        Point(x=-1, y=0)
    with pytest.raises(ValidationError):
        Point(x=0, y=-10)


def test_text_region_model():
    """Verify TextRegion model and confidence bounds."""
    region = TextRegion(
        text="File",
        bounding_box=BoundingBox(left=10, top=10, width=40, height=20),
        confidence=0.98,
        observation_id="obs-12345",
    )
    assert region.text == "File"
    assert region.confidence == 0.98
    assert region.observation_id == "obs-12345"

    # Confidence must be between 0.0 and 1.0
    with pytest.raises(ValidationError):
        TextRegion(text="Test", confidence=1.5, observation_id="obs-1")
    with pytest.raises(ValidationError):
        TextRegion(text="Test", confidence=-0.1, observation_id="obs-1")


def test_ui_element_auto_center_coordinate_mapping():
    """Verify UIElement automatically computes center point from bounding box."""
    bbox = BoundingBox(left=100, top=200, width=80, height=40)
    el = UIElement(
        element_type="button",
        name="Submit",
        bounding_box=bbox,
        interaction_capabilities=["click"],
    )

    assert el.center_point is not None
    # Center X: 100 + (80 // 2) = 140; Center Y: 200 + (40 // 2) = 220
    assert el.center_point.x == 140
    assert el.center_point.y == 220
    assert el.is_enabled is True
    assert el.is_visible is True
    assert el.is_focused is False
    assert "click" in el.interaction_capabilities

    # Explicit center point should not be overwritten
    custom_point = Point(x=999, y=888)
    el_custom = UIElement(
        element_type="text_field",
        name="Search",
        bounding_box=bbox,
        center_point=custom_point,
    )
    assert el_custom.center_point.x == 999
    assert el_custom.center_point.y == 888


def test_screen_understanding_model():
    """Verify ScreenUnderstanding composite schema."""
    state = ScreenState(width=1920, height=1080, capture_id="obs-und-1")
    region = TextRegion(text="Settings", observation_id="obs-und-1")
    ui_el = UIElement(element_type="window", name="Desktop")

    understanding = ScreenUnderstanding(
        observation_id="obs-und-1",
        screen_state=state,
        active_window={"title": "Explorer", "handle": 100},
        text_regions=[region],
        ui_elements=[ui_el],
    )

    assert understanding.observation_id == "obs-und-1"
    assert understanding.screen_state.width == 1920
    assert len(understanding.text_regions) == 1
    assert len(understanding.ui_elements) == 1
    assert understanding.active_window["title"] == "Explorer"


def test_parameter_schemas_validation():
    """Verify parameter schemas reject forbidden extra keys."""
    p1 = ScreenOCRParams(observation_id="obs-1")
    assert p1.observation_id == "obs-1"
    with pytest.raises(ValidationError):
        ScreenOCRParams(extra="not allowed")

    p2 = ScreenUIElementsParams(observation_id="obs-2", window_handle=123)
    assert p2.window_handle == 123
    with pytest.raises(ValidationError):
        ScreenUIElementsParams(extra="not allowed")

    p3 = ScreenUnderstandParams()
    assert p3.observation_id is None
    with pytest.raises(ValidationError):
        ScreenUnderstandParams(extra="not allowed")


def test_vision_cache_lifecycle_and_pruning():
    """Verify VisionCache set, get, TTL expiration, and count pruning."""
    cache = VisionCache(max_items=3, ttl_seconds=0.2)

    region = TextRegion(text="Help", observation_id="obs-c1")
    el = UIElement(element_type="button", name="OK")
    state = ScreenState(width=1920, height=1080, capture_id="obs-c1")
    understanding = ScreenUnderstanding(
        observation_id="obs-c1",
        screen_state=state,
    )

    # Set and retrieve
    cache.set_ocr("obs-c1", [region])
    cache.set_ui_elements("obs-c1", [el])
    cache.set_understanding("obs-c1", understanding)

    assert cache.get_ocr("obs-c1") == [region]
    assert cache.get_ui_elements("obs-c1") == [el]
    assert cache.get_understanding("obs-c1") == understanding

    # Test count pruning: add 3 more entries
    for i in range(2, 5):
        cache.set_ocr(f"obs-c{i}", [region])

    # Total entries should be pruned to max_items (3)
    assert len(cache._ocr_cache) <= 3
    # Oldest (obs-c1) should have been evicted
    assert cache.get_ocr("obs-c1") is None

    # Test TTL expiration
    time.sleep(0.3)
    assert cache.get_ocr("obs-c4") is None

    # Test clear
    cache.set_ocr("obs-fresh", [region])
    assert cache.get_ocr("obs-fresh") is not None
    cache.clear()
    assert cache.get_ocr("obs-fresh") is None
