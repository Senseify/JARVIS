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


class TaskStatus(str, Enum):
    """Execution status of a task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    """Types of structured runtime events emitted by JARVIS."""

    TASK_CREATED = "task_created"
    TASK_STATE_CHANGED = "task_state_changed"
    TASK_STATUS_CHANGED = "task_status_changed"
    ACTION_STARTED = "action_started"
    ACTION_COMPLETED = "action_completed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_COMPLETED = "recovery_completed"
    MEMORY_STORED = "memory_stored"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    VOICE_INPUT_RECEIVED = "voice_input_received"
    VOICE_TRANSCRIPTION_COMPLETED = "voice_transcription_completed"
    VOICE_SYNTHESIS_STARTED = "voice_synthesis_started"
    VOICE_SYNTHESIS_COMPLETED = "voice_synthesis_completed"
    VOICE_ERROR = "voice_error"


class DeviceType(str, Enum):
    """Authorized device types in the JARVIS architecture."""

    WINDOWS_HOST = "windows_host"
    IPAD_COMPANION = "ipad_companion"
    GENERIC_HOST = "generic_host"


class DeviceStatus(str, Enum):
    """Connection status for registered devices."""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"


APP_NAME = "JARVIS OS"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_DB_PATH = "jarvis.db"
