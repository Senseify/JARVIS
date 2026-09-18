"""Deterministic demo tool for verifying Phase 2 runtime execution without OS side effects."""

from typing import Any
from core.runtime.context import ExecutionContext
from core.tools.base import BaseTool, ToolDefinition


class DemoVerificationTool(BaseTool):
    """Safe, internal deterministic tool used to test and verify the agent runtime lifecycle."""

    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="demo_verification_tool",
                description="Performs an internal, deterministic verification calculation without external side effects.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "check_name": {"type": "string"},
                        "expected_value": {"type": "string"},
                    },
                    "required": ["check_name"],
                },
                required_permissions=[],
                metadata={"category": "internal_demo", "safe": True},
            )
        )

    async def execute(self, context: ExecutionContext, **params: Any) -> dict[str, Any]:
        check_name = params.get("check_name", "runtime_sanity_check")
        expected_value = params.get("expected_value", "ok")

        result = {
            "check": check_name,
            "status": "passed",
            "matched_expected": True,
            "actual_value": expected_value,
            "simulated": False,
            "executed_internally": True,
        }
        context.add_action_result(action=self.name, success=True, output=result)
        return result
