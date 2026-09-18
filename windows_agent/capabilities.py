"""Capability registry and safe standard capabilities for Windows Agent."""

from datetime import datetime, timezone
import logging
import platform
import sys
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

CapabilityHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]


class CapabilityRegistry:
    """Registry maintaining authorized, safe machine-side capabilities."""

    def __init__(self, agent_version: str = "0.1.0", start_time: Optional[float] = None):
        self.agent_version = agent_version
        self.start_time = start_time or time.time()
        self._capabilities: Dict[str, Dict[str, Any]] = {}
        self._register_default_capabilities()

    def register(self, name: str, handler: CapabilityHandler, description: str = "") -> None:
        """Register a capability handler."""
        self._capabilities[name] = {
            "handler": handler,
            "description": description,
        }
        logger.info(f"Registered capability: {name}")

    def list_capabilities(self) -> List[str]:
        """List all supported capability names."""
        return sorted(list(self._capabilities.keys()))

    def has_capability(self, name: str) -> bool:
        """Check if capability is supported."""
        return name in self._capabilities

    async def execute(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a capability handler and return structured result."""
        if name not in self._capabilities:
            raise KeyError(f"Unsupported capability: '{name}'. Supported: {self.list_capabilities()}")
        handler = self._capabilities[name]["handler"]
        return await handler(params)

    def _register_default_capabilities(self) -> None:
        """Register initial safe capabilities."""

        # 1. agent.ping
        async def ping_handler(params: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "pong": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_version": self.agent_version,
            }

        # 2. system.info
        async def system_info_handler(params: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "hostname": platform.node(),
                "python_version": platform.python_version(),
                "agent_version": self.agent_version,
                "is_windows": sys.platform == "win32",
            }

        # 3. agent.status
        async def agent_status_handler(params: Dict[str, Any]) -> Dict[str, Any]:
            uptime = time.time() - self.start_time
            return {
                "status": "online",
                "uptime_seconds": round(uptime, 2),
                "agent_version": self.agent_version,
                "registered_capabilities": self.list_capabilities(),
            }

        self.register("agent.ping", ping_handler, "Returns a heartbeat pong response from the agent.")
        self.register("system.info", system_info_handler, "Reports host platform and environment information.")
        self.register("agent.status", agent_status_handler, "Reports agent uptime and status.")
