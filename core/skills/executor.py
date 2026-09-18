"""Deterministic SkillExecutor coordinating step execution, capability checking, verification, and memory recording."""

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from core.devices.agent_bridge import AgentBridge
from core.memory.service import MemoryService
from core.models.memory import MemoryType
from core.models.protocol import CommandResultPayload
from core.models.skills import (
    SkillDefinition,
    SkillExecuteRequest,
    SkillExecution,
    SkillResult,
    SkillStep,
    SkillStepResult,
)
from core.skills.registry import SkillRegistry
from core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

CommandDispatcher = Callable[[str, str, Dict[str, Any], float], Awaitable[Dict[str, Any]]]


def interpolate_template(template: Any, inputs: Dict[str, Any]) -> Any:
    """Recursively replace `{key}` placeholders in strings, dicts, and lists with input values.

    If a string exactly matches `"{key}"`, the typed value from `inputs[key]` is returned directly.
    """
    if isinstance(template, str):
        trimmed = template.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            var_name = trimmed[1:-1]
            if var_name in inputs:
                return inputs[var_name]
        # Otherwise do partial string interpolation
        result = template
        for k, v in inputs.items():
            result = result.replace(f"{{{k}}}", str(v) if v is not None else "")
        return result
    elif isinstance(template, dict):
        return {k: interpolate_template(v, inputs) for k, v in template.items()}
    elif isinstance(template, list):
        return [interpolate_template(item, inputs) for item in template]
    return template


class SkillExecutor:
    """Executes multi-step skills with capability validation, verification checks, and memory logging."""

    def __init__(
        self,
        registry: SkillRegistry,
        agent_bridge: Optional[AgentBridge] = None,
        tool_registry: Optional[ToolRegistry] = None,
        memory_service: Optional[MemoryService] = None,
        command_dispatcher: Optional[CommandDispatcher] = None,
    ):
        self.registry = registry
        self.agent_bridge = agent_bridge
        self.tool_registry = tool_registry
        self.memory_service = memory_service
        self.command_dispatcher = command_dispatcher

    async def execute(
        self,
        skill_id: str,
        request: SkillExecuteRequest,
    ) -> SkillResult:
        """Execute a registered skill following the strict: Agent -> Skill -> Tools -> Verify -> Result -> Memory flow."""
        skill = self.registry.get_skill(skill_id)
        if not skill:
            raise KeyError(f"Skill '{skill_id}' is not registered.")

        # 1. Validate inputs against skill input schema
        resolved_inputs = self._validate_and_resolve_inputs(skill, request.inputs)

        # 2. Resolve target device and check required capabilities
        target_device_id, available_caps = self._resolve_device_and_capabilities(skill, request.device_id)
        is_satisfied, missing = self.registry.check_capabilities(skill.id, available_caps)
        if not is_satisfied:
            raise ValueError(
                f"Cannot execute skill '{skill.id}'. Target device '{target_device_id}' "
                f"is missing required capabilities: {missing}"
            )

        # 3. Create execution context
        execution = SkillExecution(
            skill_id=skill.id,
            inputs=resolved_inputs,
            status="running",
        )

        start_time = time.time()
        overall_success = True
        final_output: Dict[str, Any] = {}
        failure_error: Optional[str] = None

        # 4. Execute steps in sequential order
        for step in skill.steps:
            elapsed = time.time() - start_time
            remaining_timeout = skill.timeout - elapsed
            if remaining_timeout <= 0:
                overall_success = False
                failure_error = f"Skill execution exceeded overall timeout of {skill.timeout}s."
                execution.status = "timed_out"
                step_res = SkillStepResult(
                    step_id=step.step_id,
                    capability=step.capability,
                    status="skipped",
                    success=False,
                    error=failure_error,
                )
                execution.step_results.append(step_res)
                break

            step_timeout = min(step.timeout, remaining_timeout)
            step_params = interpolate_template(step.parameters_template, resolved_inputs)

            step_start = time.time()
            step_result = await self._execute_step(
                step=step,
                params=step_params,
                device_id=target_device_id,
                timeout=step_timeout,
            )
            step_duration_ms = round((time.time() - step_start) * 1000, 2)
            step_result.duration_ms = step_duration_ms
            execution.step_results.append(step_result)

            if step_result.output:
                final_output.update(step_result.output)

            # Check for failure (either action execution failure or verification failure)
            if not step_result.success:
                overall_success = False
                failure_error = step_result.error or "Step failed verification or execution."
                if not step.continue_on_failure:
                    logger.warning(
                        f"Skill '{skill.id}' halted at step '{step.step_id}': {failure_error}"
                    )
                    break

        total_duration_ms = round((time.time() - start_time) * 1000, 2)
        final_status = "completed" if overall_success else (execution.status if execution.status == "timed_out" else "failed")
        execution.status = final_status
        execution.completed_at = datetime.now(timezone.utc)
        execution.result = final_output
        execution.error = failure_error

        skill_res = SkillResult(
            execution_id=execution.execution_id,
            skill_id=skill.id,
            success=overall_success,
            status=final_status,
            step_results=execution.step_results,
            output=final_output,
            error=failure_error,
            duration_ms=total_duration_ms,
        )

        # 5. Record final outcome to MemoryService if available (no step-level spam)
        if self.memory_service is not None:
            try:
                mem_content = (
                    f"Skill execution: {skill.name} ({skill.id}) - "
                    f"{'Success' if overall_success else 'Failure: ' + (failure_error or 'unknown error')}"
                )
                tags = ["skill", skill.id, "success" if overall_success else "failure"]
                mem_meta = {
                    "skill_id": skill.id,
                    "execution_id": skill_res.execution_id,
                    "success": overall_success,
                    "device_id": target_device_id,
                    "error": failure_error,
                    "steps_count": len(skill_res.step_results),
                }
                if request.task_id:
                    mem_meta["task_id"] = request.task_id

                entry, _ = await self.memory_service.store_memory(
                    content=mem_content,
                    memory_type=MemoryType.OUTCOME,
                    metadata=mem_meta,
                    source="skill_engine",
                    task_id=request.task_id,
                    importance=0.7 if overall_success else 0.8,
                    tags=tags,
                )
                skill_res.memory_persisted = True
                skill_res.memory_id = entry.id
                execution.memory_id = entry.id
            except Exception as e:
                logger.error(f"Failed to record skill execution outcome in MemoryService: {e}")

        return skill_res

    def _validate_and_resolve_inputs(
        self,
        skill: SkillDefinition,
        raw_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ensure all required parameters in input_schema are supplied and inject default values."""
        resolved = dict(raw_inputs)
        schema = skill.input_schema or {}

        for param, spec in schema.items():
            if isinstance(spec, dict):
                is_required = spec.get("required", False)
                default_val = spec.get("default")
                if param not in resolved or resolved[param] is None:
                    if is_required:
                        raise ValueError(f"Missing required input parameter: '{param}'")
                    if default_val is not None:
                        resolved[param] = default_val
            elif param not in resolved:
                raise ValueError(f"Missing required input parameter: '{param}'")

        return resolved

    def _resolve_device_and_capabilities(
        self,
        skill: SkillDefinition,
        requested_device_id: Optional[str],
    ) -> tuple[str, List[str]]:
        """Identify target device ID and collect its registered capabilities."""
        # If command_dispatcher is provided, assume all required capabilities are mock-handled
        if self.command_dispatcher is not None:
            return requested_device_id or "mock_device", list(skill.required_capabilities)

        if not self.agent_bridge:
            # If no agent bridge or dispatcher, check if capabilities can be satisfied by tool_registry
            available = []
            if self.tool_registry:
                available = [t.name for t in self.tool_registry.list_tools()]
            return "local_core", available

        connected_devices = self.agent_bridge.list_connected_devices()
        if requested_device_id:
            if requested_device_id not in connected_devices:
                raise KeyError(f"Target device '{requested_device_id}' is not connected to Core.")
            session = self.agent_bridge.get_session(requested_device_id)
            caps = session.registration.capabilities if session else []
            return requested_device_id, caps

        if not connected_devices:
            raise ValueError(
                f"Cannot execute skill '{skill.id}': No machine agents currently connected to Core."
            )

        # Default to first connected device
        chosen_id = connected_devices[0]
        session = self.agent_bridge.get_session(chosen_id)
        caps = session.registration.capabilities if session else []
        return chosen_id, caps

    async def _execute_step(
        self,
        step: SkillStep,
        params: Dict[str, Any],
        device_id: str,
        timeout: float,
    ) -> SkillStepResult:
        """Dispatch a single capability step to the target machine agent or local tool."""
        try:
            # 1. Check custom command_dispatcher (e.g. for testing)
            if self.command_dispatcher is not None:
                raw_result = await self.command_dispatcher(device_id, step.capability, params, timeout)
            # 2. Check AgentBridge
            elif self.agent_bridge is not None and self.agent_bridge.is_connected(device_id):
                cmd_res: CommandResultPayload = await self.agent_bridge.send_command(
                    device_id=device_id,
                    capability=step.capability,
                    parameters=params,
                    timeout=timeout,
                )
                if not cmd_res.success:
                    return SkillStepResult(
                        step_id=step.step_id,
                        capability=step.capability,
                        status="failed",
                        success=False,
                        output=cmd_res.result,
                        error=cmd_res.error or f"Capability '{step.capability}' failed on device {device_id}.",
                    )
                raw_result = cmd_res.result or {}
            # 3. Check local ToolRegistry
            elif self.tool_registry is not None and self.tool_registry.has_tool(step.capability):
                raw_result = await self.tool_registry.execute_tool(step.capability, None, **params)
            else:
                raise RuntimeError(
                    f"No available handler found for capability '{step.capability}' on device '{device_id}'."
                )

            # Analyze output for success and verification results
            verified = None
            verification_details = None
            step_success = True
            error_msg = None

            if isinstance(raw_result, dict):
                # Check top-level success flag
                if raw_result.get("success") is False:
                    step_success = False
                    error_msg = raw_result.get("failure_reason") or raw_result.get("error") or "Capability reported failure."

                # Check verification flag if action.verify was executed
                if "verified" in raw_result:
                    verified = bool(raw_result["verified"])
                    verification_details = raw_result.get("verification")
                    if not verified:
                        step_success = False
                        error_msg = raw_result.get("failure_reason") or "Step verification condition failed."

            return SkillStepResult(
                step_id=step.step_id,
                capability=step.capability,
                status="success" if step_success else "failed",
                success=step_success,
                output=raw_result if isinstance(raw_result, dict) else {"raw": raw_result},
                error=error_msg,
                verified=verified,
                verification_details=verification_details,
            )

        except asyncio.TimeoutError:
            return SkillStepResult(
                step_id=step.step_id,
                capability=step.capability,
                status="failed",
                success=False,
                error=f"Step '{step.step_id}' timed out after {timeout}s.",
            )
        except Exception as e:
            return SkillStepResult(
                step_id=step.step_id,
                capability=step.capability,
                status="failed",
                success=False,
                error=str(e),
            )
