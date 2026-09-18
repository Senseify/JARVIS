"""Action receipt model capturing execution audit details for computer control commands."""

from datetime import datetime, timezone
import time
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ActionReceipt(BaseModel):
    """Structured receipt confirming the physical execution outcome and timing of an action."""

    model_config = ConfigDict(extra="ignore")

    capability: str
    request_id: Optional[str] = None
    start_time: str
    end_time: str
    duration_ms: float
    success: bool
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class ReceiptTracker:
    """Context manager / helper for measuring execution timing and generating ActionReceipts."""

    def __init__(self, capability: str, request_id: Optional[str] = None):
        self.capability = capability
        self.request_id = request_id
        self.start_wall: Optional[datetime] = None
        self.start_mono: Optional[float] = None

    def __enter__(self):
        self.start_wall = datetime.now(timezone.utc)
        self.start_mono = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def create_receipt(self, success: bool, result: Optional[dict[str, Any]] = None, error: Optional[str] = None) -> ActionReceipt:
        end_wall = datetime.now(timezone.utc)
        end_mono = time.perf_counter()
        duration_ms = round((end_mono - (self.start_mono or end_mono)) * 1000.0, 2)

        return ActionReceipt(
            capability=self.capability,
            request_id=self.request_id,
            start_time=(self.start_wall or end_wall).isoformat(),
            end_time=end_wall.isoformat(),
            duration_ms=duration_ms,
            success=success,
            result=result,
            error=error,
        )
