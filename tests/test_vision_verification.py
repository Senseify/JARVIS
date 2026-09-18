"""Tests for vision verification primitives: OCR text presence/absence and native UI element checks."""

import pytest

from windows_agent.observation.verifier import VerificationEngine
from windows_agent.vision.models import BoundingBox, TextRegion, UIElement


def test_verify_text_present():
    """Verify OCR text presence detection and failure reporting."""
    engine = VerificationEngine()
    regions = [
        TextRegion(text="Welcome to JARVIS OS", observation_id="obs-1"),
        TextRegion(text="Settings and Configuration", observation_id="obs-1"),
    ]

    # Substring match (case-insensitive)
    res_ok = engine.verify_text_present("settings", regions)
    assert res_ok.passed is True
    assert "Settings and Configuration" in res_ok.observed_state
    assert res_ok.failure_reason is None

    # Case-sensitive match
    res_cs_fail = engine.verify_text_present("settings", regions, case_sensitive=True)
    assert res_cs_fail.passed is False
    assert "Expected text 'settings' not found" in res_cs_fail.failure_reason

    res_cs_ok = engine.verify_text_present("Settings", regions, case_sensitive=True)
    assert res_cs_ok.passed is True

    # Missing text
    res_missing = engine.verify_text_present("Bluetooth", regions)
    assert res_missing.passed is False
    assert "Expected text 'Bluetooth' not found" in res_missing.failure_reason


def test_verify_text_absent():
    """Verify check confirming text is absent from OCR regions."""
    engine = VerificationEngine()
    regions = [
        TextRegion(text="Status: Active", observation_id="obs-2"),
    ]

    # Absent
    res_absent = engine.verify_text_absent("Error", regions)
    assert res_absent.passed is True
    assert res_absent.failure_reason is None

    # Present (should fail)
    res_present = engine.verify_text_absent("Active", regions)
    assert res_present.passed is False
    assert "unexpectedly present" in res_present.failure_reason


def test_verify_ui_element_primitives():
    """Verify UI element matching by name, type, enabled state, and visibility."""
    engine = VerificationEngine()
    elements = [
        UIElement(
            element_id="btn-save",
            element_type="button",
            name="Save Changes",
            is_enabled=True,
            is_visible=True,
        ),
        UIElement(
            element_id="btn-delete",
            element_type="button",
            name="Delete Item",
            is_enabled=False,
            is_visible=True,
        ),
        UIElement(
            element_id="chk-auto",
            element_type="checkbox",
            name="Auto-update",
            is_enabled=True,
            is_visible=False,
        ),
        UIElement(
            element_id="txt-search",
            element_type="text_field",
            name="Search",
            is_enabled=True,
            is_visible=True,
        ),
    ]

    # 1. Match by name
    res_name = engine.verify_ui_element(elements, name="Save")
    assert res_name.passed is True
    assert len(res_name.observed_state) == 1

    # 2. Match by type
    res_type = engine.verify_ui_element(elements, element_type="button")
    assert res_type.passed is True
    assert len(res_type.observed_state) == 2

    # 3. Match by enabled state
    res_disabled_btn = engine.verify_ui_element(elements, element_type="button", is_enabled=False)
    assert res_disabled_btn.passed is True
    assert res_disabled_btn.observed_state[0]["id"] == "btn-delete"

    # 4. Match by visibility
    res_hidden_chk = engine.verify_ui_element(elements, element_type="checkbox", is_visible=False)
    assert res_hidden_chk.passed is True

    # 5. Non-matching combination (Delete button that is enabled)
    res_fail = engine.verify_ui_element(elements, name="Delete", is_enabled=True)
    assert res_fail.passed is False
    assert "No UI element matching" in res_fail.failure_reason

    # 6. Non-existent element
    res_missing = engine.verify_ui_element(elements, name="NonExistentControl")
    assert res_missing.passed is False
    assert "No UI element matching" in res_missing.failure_reason


def test_verify_condition_dispatch_vision():
    """Verify verify_condition dispatches text and UI element checks."""
    engine = VerificationEngine()
    regions = [TextRegion(text="Network Connected", observation_id="obs-3")]
    elements = [
        UIElement(
            element_id="ctrl-1",
            element_type="button",
            name="Connect",
            is_enabled=True,
            is_visible=True,
        )
    ]

    # text_present
    r1 = engine.verify_condition("text_present", "Connected", text_regions=regions)
    assert r1.passed is True

    # text_absent
    r2 = engine.verify_condition("text_absent", "Disconnected", text_regions=regions)
    assert r2.passed is True

    # ui_element (string name)
    r3 = engine.verify_condition("ui_element", "Connect", ui_elements=elements)
    assert r3.passed is True

    # ui_element (dict with type and name)
    r4 = engine.verify_condition(
        "ui_element",
        {"name": "Connect", "type": "button", "enabled": True},
        ui_elements=elements,
    )
    assert r4.passed is True

    # ui_element_visible
    r5 = engine.verify_condition("ui_element_visible", "Connect", ui_elements=elements)
    assert r5.passed is True

    # ui_element_enabled
    r6 = engine.verify_condition("ui_element_enabled", "Connect", ui_elements=elements)
    assert r6.passed is True

    # Missing text_regions raises ValueError
    with pytest.raises(ValueError, match="Text regions required"):
        engine.verify_condition("text_present", "Connected")

    # Missing ui_elements raises ValueError
    with pytest.raises(ValueError, match="UI elements required"):
        engine.verify_condition("ui_element", "Connect")
