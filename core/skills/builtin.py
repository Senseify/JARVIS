"""Built-in deterministic skills for JARVIS OS composing existing capabilities."""

from typing import List
from core.models.skills import SkillDefinition, SkillStep


def create_launch_and_verify_skill() -> SkillDefinition:
    """Skill to launch an allowlisted application and verify window presence."""
    return SkillDefinition(
        id="launch_and_verify",
        name="Launch and Verify Application",
        description="Launch an allowlisted application and verify that its window is active and running.",
        version="0.1.0",
        required_capabilities=["app.launch", "window.list", "action.verify"],
        steps=[
            SkillStep(
                step_id="launch_and_verify_window",
                name="Launch Application and Verify Window",
                capability="action.verify",
                parameters_template={
                    "action_capability": "app.launch",
                    "action_parameters": {
                        "app_name": "{app_name}",
                    },
                    "expected_condition": "window_open",
                    "expected_value": "{window_title}",
                },
                expected_condition="window_open",
                expected_value="{window_title}",
                timeout=15.0,
            )
        ],
        timeout=30.0,
        verification_requirements={"condition": "window_open", "target": "window_title"},
        input_schema={
            "app_name": {"type": "string", "required": True, "description": "Allowlisted application name (e.g. notepad, calc)"},
            "window_title": {"type": "string", "required": False, "default": "", "description": "Expected window title substring"},
        },
        output_schema={
            "verified": {"type": "boolean"},
            "action_receipt": {"type": "object"},
        },
        metadata={"category": "application_control", "deterministic": True},
    )


def create_type_and_verify_skill() -> SkillDefinition:
    """Skill to type supplied text into active window and optionally verify text presence."""
    return SkillDefinition(
        id="type_and_verify",
        name="Type Text and Verify",
        description="Type text into active foreground application with optional OCR verification.",
        version="0.1.0",
        required_capabilities=["keyboard.type", "action.verify"],
        steps=[
            SkillStep(
                step_id="type_and_verify_text",
                name="Type Text with Verification",
                capability="action.verify",
                parameters_template={
                    "action_capability": "keyboard.type",
                    "action_parameters": {
                        "text": "{text}",
                    },
                    "expected_condition": "{expected_condition}",
                    "expected_value": "{expected_value}",
                },
                expected_condition="{expected_condition}",
                expected_value="{expected_value}",
                timeout=15.0,
            )
        ],
        timeout=30.0,
        verification_requirements={"condition": "{expected_condition}", "target": "{expected_value}"},
        input_schema={
            "text": {"type": "string", "required": True, "description": "Text to type into active window"},
            "expected_condition": {"type": "string", "required": False, "default": "none", "description": "Optional condition, e.g. text_present"},
            "expected_value": {"type": "string", "required": False, "default": "", "description": "Expected text snippet for OCR verification"},
        },
        output_schema={
            "verified": {"type": "boolean"},
            "action_receipt": {"type": "object"},
        },
        metadata={"category": "input_automation", "deterministic": True},
    )


def create_click_and_verify_skill() -> SkillDefinition:
    """Skill to click at coordinates and observe/verify desktop UI state."""
    return SkillDefinition(
        id="click_and_verify",
        name="Click and Verify UI State",
        description="Perform mouse click at specified coordinates and verify expected desktop or UI condition.",
        version="0.1.0",
        required_capabilities=["mouse.click", "action.verify"],
        steps=[
            SkillStep(
                step_id="click_and_verify_state",
                name="Click Coordinates and Verify State",
                capability="action.verify",
                parameters_template={
                    "action_capability": "mouse.click",
                    "action_parameters": {
                        "x": "{x}",
                        "y": "{y}",
                        "button": "{button}",
                    },
                    "expected_condition": "{expected_condition}",
                    "expected_value": "{expected_value}",
                },
                expected_condition="{expected_condition}",
                expected_value="{expected_value}",
                timeout=15.0,
            )
        ],
        timeout=30.0,
        verification_requirements={"condition": "{expected_condition}", "target": "{expected_value}"},
        input_schema={
            "x": {"type": "integer", "required": False, "description": "X coordinate on screen"},
            "y": {"type": "integer", "required": False, "description": "Y coordinate on screen"},
            "button": {"type": "string", "required": False, "default": "left", "description": "Mouse button ('left', 'right', 'middle')"},
            "expected_condition": {"type": "string", "required": False, "default": "none", "description": "Verification condition"},
            "expected_value": {"type": "any", "required": False, "default": None, "description": "Expected value for verification condition"},
        },
        output_schema={
            "verified": {"type": "boolean"},
            "action_receipt": {"type": "object"},
        },
        metadata={"category": "input_automation", "deterministic": True},
    )


def get_builtin_skills() -> List[SkillDefinition]:
    """Return all standard built-in generic skill definitions."""
    return [
        create_launch_and_verify_skill(),
        create_type_and_verify_skill(),
        create_click_and_verify_skill(),
    ]
