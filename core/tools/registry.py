"""Tool and skill registry for JARVIS OS."""

import logging
from typing import Dict, List, Optional
from core.runtime.context import ExecutionContext
from core.tools.base import BaseTool, ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry maintaining available tools and execution dispatch."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if tool.name in self._tools:
            logger.warning(f"Overwriting existing tool registration: {tool.name}")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def unregister_tool(self, name: str) -> bool:
        """Unregister a tool by name."""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
            return True
        return False

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Retrieve a registered tool by name."""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> List[ToolDefinition]:
        """List metadata for all registered tools."""
        return [tool.definition for tool in self._tools.values()]

    async def execute_tool(self, name: str, context: ExecutionContext, **params) -> dict:
        """Dispatch execution to a named tool."""
        tool = self.get_tool(name)
        if not tool:
            raise KeyError(f"Tool '{name}' is not registered.")
        return await tool.execute(context, **params)
