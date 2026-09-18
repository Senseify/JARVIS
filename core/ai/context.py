"""Conversational context manager supporting follow-ups, pronoun resolution, and bounded history."""

import re
from typing import Any
from core.models.ai import ChatMessage, ModelRole


class ConversationContext:
    """Maintains bounded conversation history and tracks active application/task state.

    Enables follow-up resolution, e.g. 'Open Notepad' followed by 'Type hello into it'.
    """

    def __init__(self, session_id: str = "default", max_turns: int = 20) -> None:
        self.session_id = session_id
        self.max_turns = max_turns
        self.messages: list[ChatMessage] = []
        self.active_task_id: str | None = None
        self.active_app: str | None = None
        self.last_target_window: str | None = None
        self.last_tool_result: Any | None = None

    def add_message(self, role: ModelRole, content: str) -> None:
        """Add a message turn while maintaining bounded length."""
        self.messages.append(ChatMessage(role=role, content=content))
        if len(self.messages) > self.max_turns:
            # Preserve system messages if any, truncate oldest non-system
            system_msgs = [m for m in self.messages if m.role == ModelRole.SYSTEM]
            recent_msgs = [m for m in self.messages if m.role != ModelRole.SYSTEM][-self.max_turns :]
            self.messages = system_msgs + recent_msgs

    def update_active_app(self, app_name: str | None) -> None:
        """Update the currently focused application."""
        if app_name:
            self.active_app = app_name

    def resolve_followup_references(self, text: str) -> str:
        """Resolve pronouns like 'it', 'the app', 'into it' to the active application."""
        if not self.active_app:
            return text

        resolved = text
        # "type <something> into it" -> "type <something> into <active_app>"
        resolved = re.sub(r"\binto it\b", f"into {self.active_app}", resolved, flags=re.IGNORECASE)
        # "in it" -> "in <active_app>"
        resolved = re.sub(r"\bin it\b", f"in {self.active_app}", resolved, flags=re.IGNORECASE)
        # "close it" -> "Close <active_app>" or "close <active_app>"
        resolved = re.sub(r"\bClose it\b", f"Close {self.active_app}", resolved)
        resolved = re.sub(r"\bclose it\b", f"close {self.active_app}", resolved)
        # "focus it" -> "Focus <active_app>" or "focus <active_app>"
        resolved = re.sub(r"\bFocus it\b", f"Focus {self.active_app}", resolved)
        resolved = re.sub(r"\bfocus it\b", f"focus {self.active_app}", resolved)

        return resolved

    def get_context_summary(self) -> dict[str, Any]:
        """Return structured context snapshot for prompt injection."""
        return {
            "session_id": self.session_id,
            "active_app": self.active_app,
            "active_task_id": self.active_task_id,
            "last_target_window": self.last_target_window,
            "history_length": len(self.messages),
        }
