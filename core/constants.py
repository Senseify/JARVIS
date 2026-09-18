"""Architectural constants and enumerations for JARVIS OS."""

from enum import Enum


class AgentLoopState(str, Enum):
    """Core Agent Loop states representing the lifecycle of an autonomous task."""

    IDLE = "idle"
    OBSERVE = "observe"
    UNDERSTAND = "understand"
    PLAN = "plan"
    ACT = "act"
    VERIFY = "verify"
    RECOVER = "recover"
    REMEMBER = "remember"


APP_NAME = "JARVIS OS"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
