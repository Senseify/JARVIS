"""Tests for deterministic VoiceCommandParser."""

from core.models.voice_command import VoiceCommandIntentType
from core.voice.parser import VoiceCommandParser


def test_parser_app_launch_commands():
    """Verify application launch patterns."""
    parser = VoiceCommandParser()

    intent = parser.parse("open notepad")
    assert intent.intent_type == VoiceCommandIntentType.APP_LAUNCH
    assert intent.parameters["app_name"] == "notepad"
    assert intent.parameters["window_title"] == "Notepad"

    intent_calc = parser.parse("Launch Calculator!")
    assert intent_calc.intent_type == VoiceCommandIntentType.APP_LAUNCH
    assert intent_calc.parameters["app_name"] == "calculator"

    intent_paint = parser.parse("start mspaint")
    assert intent_paint.intent_type == VoiceCommandIntentType.APP_LAUNCH
    assert intent_paint.parameters["app_name"] == "paint"


def test_parser_typing_and_pressing_commands():
    """Verify typing and keypress patterns."""
    parser = VoiceCommandParser()

    intent_type = parser.parse("type hello world")
    assert intent_type.intent_type == VoiceCommandIntentType.KEYBOARD_TYPE
    assert intent_type.parameters["text"] == "hello world"

    intent_press = parser.parse("press enter.")
    assert intent_press.intent_type == VoiceCommandIntentType.KEYBOARD_PRESS
    assert intent_press.parameters["key"] == "enter"

    intent_esc = parser.parse("hit the escape")
    assert intent_esc.intent_type == VoiceCommandIntentType.KEYBOARD_PRESS
    assert intent_esc.parameters["key"] == "esc"


def test_parser_mouse_commands():
    """Verify mouse coordinate move and click patterns."""
    parser = VoiceCommandParser()

    intent_move = parser.parse("move the mouse to 500 300")
    assert intent_move.intent_type == VoiceCommandIntentType.MOUSE_MOVE
    assert intent_move.parameters["x"] == 500
    assert intent_move.parameters["y"] == 300

    intent_click = parser.parse("click")
    assert intent_click.intent_type == VoiceCommandIntentType.MOUSE_CLICK
    assert intent_click.parameters["button"] == "left"
    assert not intent_click.parameters["double"]

    intent_double = parser.parse("double click mouse")
    assert intent_double.intent_type == VoiceCommandIntentType.MOUSE_CLICK
    assert intent_double.parameters["double"] is True

    intent_right = parser.parse("right click")
    assert intent_right.intent_type == VoiceCommandIntentType.MOUSE_CLICK
    assert intent_right.parameters["button"] == "right"


def test_parser_query_commands():
    """Verify task status and device listing queries."""
    parser = VoiceCommandParser()

    intent_task = parser.parse("what is the status of this task?")
    assert intent_task.intent_type == VoiceCommandIntentType.QUERY_TASK_STATUS

    intent_dev = parser.parse("what devices are connected")
    assert intent_dev.intent_type == VoiceCommandIntentType.QUERY_DEVICES


def test_parser_rejects_unauthorized_or_unknown_commands():
    """Verify that dangerous, arbitrary, or unknown commands map strictly to UNKNOWN."""
    parser = VoiceCommandParser()

    unauthorized = [
        "rm -rf /",
        "format C:",
        "powershell Get-Process",
        "whoami",
        "tell me a joke",
        "browse to google.com",
        "",
        "   ",
        "random gibberish 12345",
    ]

    for cmd in unauthorized:
        intent = parser.parse(cmd)
        assert intent.intent_type == VoiceCommandIntentType.UNKNOWN
        assert intent.confidence == 0.0
