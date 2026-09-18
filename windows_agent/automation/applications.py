"""Safe application launch controller using an explicit allowlist."""

import asyncio
import logging
import subprocess
import sys
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

# Default explicit allowlist of authorized applications
DEFAULT_APPLICATION_ALLOWLIST: Dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "explorer": "explorer.exe",
}


class AppLaunchParams(BaseModel):
    """Validation schema for app.launch parameters."""

    model_config = ConfigDict(extra="forbid")

    app_name: str = Field(..., min_length=1, max_length=50, description="Allowlisted application key")
    args: Optional[List[str]] = Field(default=None, max_length=20, description="Optional command-line arguments")

    @field_validator("app_name")
    @classmethod
    def sanitize_app_name(cls, v: str) -> str:
        cleaned = v.strip().lower()
        # Strictly forbid slashes, backslashes, or shell characters
        for forbidden in ["/", "\\", ";", "&", "|", "`", "$", "(", ")", "<", ">"]:
            if forbidden in cleaned:
                raise ValueError(f"Dangerous characters not allowed in app_name: '{forbidden}'")
        return cleaned

    @field_validator("args")
    @classmethod
    def sanitize_args(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        # Reject shell piping or redirection
        for arg in v:
            for forbidden in [";", "&", "|", "`", "$", "<", ">"]:
                if forbidden in arg:
                    raise ValueError(f"Dangerous shell characters not allowed in arguments: '{forbidden}'")
        return v


class ApplicationController:
    """Safely launches allowlisted desktop applications."""

    def __init__(self, allowlist: Optional[Dict[str, str]] = None, driver: Optional[Any] = None):
        self.allowlist = dict(allowlist or DEFAULT_APPLICATION_ALLOWLIST)
        self._driver = driver
        self.is_windows = sys.platform == "win32"

    def get_allowlist(self) -> List[str]:
        """Return a sorted list of allowlisted application keys."""
        return sorted(list(self.allowlist.keys()))

    def is_allowlisted(self, app_key: str) -> bool:
        """Check if an application key is in the allowlist."""
        return app_key.lower() in self.allowlist

    async def launch(self, params: AppLaunchParams) -> dict:
        """Launch an authorized application from the allowlist."""
        app_key = params.app_name.lower()

        if not self.is_allowlisted(app_key):
            allowed = self.get_allowlist()
            raise PermissionError(
                f"Application '{params.app_name}' is not authorized. "
                f"Allowed applications: {allowed}"
            )

        executable = self.allowlist[app_key]

        if self._driver:
            return await self._driver.launch(app_key, executable, params.args)

        if not self.is_windows:
            logger.info(f"[Non-Windows stub] app.launch '{app_key}' -> '{executable}'")
            return {
                "launched": True,
                "app_name": app_key,
                "executable": executable,
                "pid": 9999,
                "platform": sys.platform,
            }

        # Safe launch on Windows without shell=True
        cmd = [executable]
        if params.args:
            cmd.extend(params.args)

        proc = subprocess.Popen(
            cmd,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return {
            "launched": True,
            "app_name": app_key,
            "executable": executable,
            "pid": proc.pid,
            "success": True,
        }
