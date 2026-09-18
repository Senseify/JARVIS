"""Windows Agent package for JARVIS OS."""

from windows_agent.agent import WindowsAgent
from windows_agent.capabilities import CapabilityRegistry

__version__ = "0.1.0"

__all__ = ["WindowsAgent", "CapabilityRegistry", "__version__"]
