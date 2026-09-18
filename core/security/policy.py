"""Centralized security policy engine enforcing strict action evaluation and boundaries."""

import logging
from typing import Any
from core.models.security import ActionPolicyEvaluation, RiskLevel, SecurityPolicyConfig

logger = logging.getLogger(__name__)


class SecurityPolicyEngine:
    """Evaluates proposed actions against strict allowlists and security boundaries.

    Ensures that AI models or automated workflows cannot perform arbitrary code/shell
    execution, access sensitive paths, or launch non-allowlisted applications.
    """

    def __init__(self, config: SecurityPolicyConfig | None = None) -> None:
        self.config = config or SecurityPolicyConfig()

    def evaluate(
        self,
        tool: str,
        arguments: dict[str, Any],
        device_id: str | None = None,
    ) -> ActionPolicyEvaluation:
        """Evaluate a proposed tool call and its arguments."""
        normalized_tool = tool.strip().lower()

        # 1. Blocked tools check (shell, powershell, cmd, eval, etc.)
        for blocked in self.config.blocked_tools:
            if blocked.lower() in normalized_tool:
                logger.warning("Security violation: tool '%s' blocked by policy", tool)
                return ActionPolicyEvaluation(
                    allowed=False,
                    risk_level=RiskLevel.BLOCKED,
                    reason=f"Tool '{tool}' is explicitly blocked by security policy.",
                )

        # 2. Block keywords in tool names
        dangerous_keywords = ["shell", "exec", "eval", "cmd", "powershell", "bash", "spawn"]
        if any(k in normalized_tool for k in dangerous_keywords):
            logger.warning("Security violation: tool '%s' contains dangerous keyword", tool)
            return ActionPolicyEvaluation(
                allowed=False,
                risk_level=RiskLevel.BLOCKED,
                reason=f"Tool '{tool}' contains prohibited execution keywords.",
            )

        # 3. Read-only tools
        read_only_tools = {
            "screen.capture",
            "screen.ocr",
            "screen.ui_detect",
            "window.list",
            "window.focus",
            "action.verify",
            "device.list",
            "task.status",
            "memory.get",
            "memory.search",
        }
        if normalized_tool in read_only_tools:
            return ActionPolicyEvaluation(
                allowed=True,
                risk_level=RiskLevel.READ_ONLY,
                reason="Read-only operation allowed.",
                sanitized_arguments=dict(arguments),
            )

        # 4. Application launch validation
        if normalized_tool in ("app.launch", "app.open"):
            app_target = str(arguments.get("app") or arguments.get("name") or "").strip().lower()
            if not app_target:
                return ActionPolicyEvaluation(
                    allowed=False,
                    risk_level=RiskLevel.BLOCKED,
                    reason="Missing application target in app.launch arguments.",
                )

            # Check allowlist
            is_allowlisted = any(
                allowed.lower() in app_target or app_target in allowed.lower()
                for allowed in self.config.allowlisted_apps
            )
            if not is_allowlisted:
                logger.warning("Blocked launch of non-allowlisted application '%s'", app_target)
                return ActionPolicyEvaluation(
                    allowed=False,
                    risk_level=RiskLevel.BLOCKED,
                    reason=f"Application '{app_target}' is not in the approved allowlist.",
                )

            return ActionPolicyEvaluation(
                allowed=True,
                risk_level=RiskLevel.LOW_RISK,
                reason=f"Application '{app_target}' is allowlisted.",
                sanitized_arguments=dict(arguments),
            )

        # 5. Input automation validation (mouse and keyboard)
        input_tools = {
            "keyboard.type",
            "keyboard.press",
            "keyboard.hotkey",
            "mouse.move",
            "mouse.click",
            "mouse.double_click",
            "mouse.right_click",
        }
        if normalized_tool in input_tools:
            if normalized_tool == "keyboard.type":
                text = str(arguments.get("text", ""))
                if len(text) > self.config.max_typing_length:
                    return ActionPolicyEvaluation(
                        allowed=False,
                        risk_level=RiskLevel.BLOCKED,
                        reason=f"Typing length ({len(text)}) exceeds limit of {self.config.max_typing_length} chars.",
                    )
            return ActionPolicyEvaluation(
                allowed=True,
                risk_level=RiskLevel.MEDIUM_RISK,
                reason="Input automation allowed.",
                sanitized_arguments=dict(arguments),
            )

        # 6. Composite skills
        skill_tools = {"skill.execute", "launch_and_verify", "type_and_verify", "click_and_verify"}
        if normalized_tool in skill_tools:
            return ActionPolicyEvaluation(
                allowed=True,
                risk_level=RiskLevel.LOW_RISK,
                reason="Standard verified skill allowed.",
                sanitized_arguments=dict(arguments),
            )

        # Default deny
        logger.warning("Denying unrecognized tool '%s'", tool)
        return ActionPolicyEvaluation(
            allowed=False,
            risk_level=RiskLevel.BLOCKED,
            reason=f"Tool '{tool}' is not registered or permitted by policy.",
        )
