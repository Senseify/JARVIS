"""Deterministic voice command parser mapping natural speech transcripts to safe JARVIS actions."""

import re
from typing import Optional

from core.models.voice_command import VoiceCommandIntent, VoiceCommandIntentType


class VoiceCommandParser:
    """Deterministic parser matching recognized speech against allowlisted commands."""

    # 1. Application launch regex
    _APP_PATTERN = re.compile(
        r"^(?:open|launch|start)(?:\s+the)?\s+(notepad|calc|calculator|paint|mspaint|explorer)$",
        re.IGNORECASE,
    )

    # 2. Keyboard typing regex
    _TYPE_PATTERN = re.compile(
        r"^(?:type|enter|write)(?:\s+(?:text|message))?\s+(.+)$",
        re.IGNORECASE,
    )

    # 3. Key press regex
    _PRESS_PATTERN = re.compile(
        r"^(?:press|hit)(?:\s+the)?\s+(enter|return|tab|esc|escape|space|backspace|up|down|left|right)$",
        re.IGNORECASE,
    )

    # 4. Mouse move regex: e.g. "move the mouse to 500 300", "move mouse to 100 200"
    _MOUSE_MOVE_PATTERN = re.compile(
        r"^(?:move|set)(?:\s+the)?\s+(?:mouse|cursor)(?:\s+position)?\s+to\s+(-?\d+)\s+[, ]?\s*(-?\d+)$",
        re.IGNORECASE,
    )

    # 5. Mouse click regex: e.g. "click", "left click", "double click", "right click"
    _MOUSE_CLICK_PATTERN = re.compile(
        r"^(?:(double|right|left)\s+)?click(?:\s+(?:the\s+)?mouse)?(?:\s+(?:button|here))?$",
        re.IGNORECASE,
    )

    # 6. Query task status regex
    _QUERY_TASK_PATTERN = re.compile(
        r"^(?:what\s+is\s+the\s+status\s+of\s+this\s+task|what\s+is\s+the\s+task\s+status|task\s+status|check\s+task(?:\s+status)?)$",
        re.IGNORECASE,
    )

    # 7. Query devices regex
    _QUERY_DEVICES_PATTERN = re.compile(
        r"^(?:what\s+devices\s+are\s+connected|which\s+devices\s+are\s+online|list\s+devices|connected\s+devices|device\s+status)$",
        re.IGNORECASE,
    )

    def parse(self, transcript: Optional[str]) -> VoiceCommandIntent:
        """Parse raw speech transcript into a structured VoiceCommandIntent."""
        if not transcript:
            return VoiceCommandIntent(
                intent_type=VoiceCommandIntentType.UNKNOWN,
                action_target="",
                parameters={"reason": "empty_transcript"},
                confidence=0.0,
            )

        # Normalize text: strip punctuation from extremities and lowercase
        cleaned = transcript.strip().strip(".?!,;").strip().lower()
        if not cleaned:
            return VoiceCommandIntent(
                intent_type=VoiceCommandIntentType.UNKNOWN,
                action_target="",
                parameters={"reason": "whitespace_only"},
                confidence=0.0,
            )

        # 1. Application Launch
        app_match = self._APP_PATTERN.match(cleaned)
        if app_match:
            raw_app = app_match.group(1).lower()
            app_map = {
                "notepad": ("notepad", "Notepad"),
                "calculator": ("calculator", "Calculator"),
                "calc": ("calculator", "Calculator"),
                "paint": ("paint", "Paint"),
                "mspaint": ("paint", "Paint"),
                "explorer": ("explorer", "Explorer"),
            }
            target_app, win_title = app_map.get(raw_app, (raw_app, raw_app.capitalize()))
            return VoiceCommandIntent(
                intent_type=VoiceCommandIntentType.APP_LAUNCH,
                action_target=target_app,
                parameters={"app_name": target_app, "window_title": win_title},
                confidence=1.0,
                matched_pattern="app_launch",
            )

        # 2. Keyboard Type
        type_match = self._TYPE_PATTERN.match(cleaned)
        if type_match:
            text_to_type = type_match.group(1).strip()
            # Strip outer quotes if present
            if (text_to_type.startswith('"') and text_to_type.endswith('"')) or (
                text_to_type.startswith("'") and text_to_type.endswith("'")
            ):
                text_to_type = text_to_type[1:-1].strip()
            return VoiceCommandIntent(
                intent_type=VoiceCommandIntentType.KEYBOARD_TYPE,
                action_target=text_to_type,
                parameters={"text": text_to_type},
                confidence=1.0,
                matched_pattern="keyboard_type",
            )

        # 3. Keyboard Press
        press_match = self._PRESS_PATTERN.match(cleaned)
        if press_match:
            key = press_match.group(1).lower()
            if key in ("return", "enter"):
                key = "enter"
            elif key in ("escape", "esc"):
                key = "esc"
            return VoiceCommandIntent(
                intent_type=VoiceCommandIntentType.KEYBOARD_PRESS,
                action_target=key,
                parameters={"key": key},
                confidence=1.0,
                matched_pattern="keyboard_press",
            )

        # 4. Mouse Move
        move_match = self._MOUSE_MOVE_PATTERN.match(cleaned)
        if move_match:
            x_coord = int(move_match.group(1))
            y_coord = int(move_match.group(2))
            return VoiceCommandIntent(
                intent_type=VoiceCommandIntentType.MOUSE_MOVE,
                action_target=f"{x_coord},{y_coord}",
                parameters={"x": x_coord, "y": y_coord},
                confidence=1.0,
                matched_pattern="mouse_move",
            )

        # 5. Mouse Click
        click_match = self._MOUSE_CLICK_PATTERN.match(cleaned)
        if click_match:
            modifier = (click_match.group(1) or "left").lower()
            button = "right" if modifier == "right" else "left"
            is_double = modifier == "double"
            return VoiceCommandIntent(
                intent_type=VoiceCommandIntentType.MOUSE_CLICK,
                action_target=modifier,
                parameters={"button": button, "double": is_double},
                confidence=1.0,
                matched_pattern="mouse_click",
            )

        # 6. Query Task Status
        if self._QUERY_TASK_PATTERN.match(cleaned):
            return VoiceCommandIntent(
                intent_type=VoiceCommandIntentType.QUERY_TASK_STATUS,
                action_target="task_status",
                parameters={},
                confidence=1.0,
                matched_pattern="query_task_status",
            )

        # 7. Query Devices
        if self._QUERY_DEVICES_PATTERN.match(cleaned):
            return VoiceCommandIntent(
                intent_type=VoiceCommandIntentType.QUERY_DEVICES,
                action_target="devices",
                parameters={},
                confidence=1.0,
                matched_pattern="query_devices",
            )

        # Unrecognized command
        return VoiceCommandIntent(
            intent_type=VoiceCommandIntentType.UNKNOWN,
            action_target="",
            parameters={"raw_transcript": cleaned},
            confidence=0.0,
            matched_pattern=None,
        )
