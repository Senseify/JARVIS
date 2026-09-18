"""Autonomous multi-step planner translating user goals into validated dependency graphs."""

import logging
from typing import Any
from core.models.ai import ToolCallDefinition
from core.models.planning import Plan, PlanStatus, PlanStep, StepStatus
from core.security.policy import SecurityPolicyEngine
from core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AutonomousPlanner:
    """Generates, validates, and manages multi-step execution plans."""

    def __init__(
        self,
        security_policy: SecurityPolicyEngine | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.security_policy = security_policy or SecurityPolicyEngine()
        self.tool_registry = tool_registry or ToolRegistry()
        self._plans: dict[str, Plan] = {}

    def create_plan_from_tool_calls(
        self,
        goal: str,
        tool_calls: list[ToolCallDefinition],
        device_id: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> Plan:
        """Construct a validated multi-step plan from ordered tool calls."""
        steps: list[PlanStep] = []
        previous_step_id: str | None = None

        for idx, call in enumerate(tool_calls):
            # 1. Policy validation
            eval_result = self.security_policy.evaluate(call.tool, call.arguments, device_id)
            if not eval_result.allowed:
                raise PermissionError(
                    f"Plan creation rejected by security policy: {eval_result.reason}"
                )

            # 2. Determine verification requirements
            # Read-only operations do not require post-verification; actions modifying state do
            needs_verification = call.tool not in {
                "screen.capture",
                "screen.ocr",
                "screen.ui_detect",
                "window.list",
                "action.verify",
            }

            step = PlanStep(
                name=f"{call.tool} (step {idx + 1})",
                tool=call.tool,
                arguments=eval_result.sanitized_arguments,
                depends_on=[previous_step_id] if previous_step_id else [],
                verification_required=needs_verification,
                status=StepStatus.PENDING,
            )
            steps.append(step)
            previous_step_id = step.step_id

        plan = Plan(
            goal=goal,
            steps=steps,
            status=PlanStatus.PENDING,
            timeout_seconds=timeout_seconds,
            device_id=device_id,
        )
        self._plans[plan.plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> Plan | None:
        """Retrieve an existing plan by ID."""
        return self._plans.get(plan_id)

    def list_plans(self) -> list[Plan]:
        """List all tracked plans."""
        return list(self._plans.values())
