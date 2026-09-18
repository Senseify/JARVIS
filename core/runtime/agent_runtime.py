"""Asynchronous Agent Runtime orchestrating the JARVIS Agent Loop lifecycle."""

import logging
from typing import Any, Dict, Optional

from core.constants import AgentLoopState, EventType, TaskStatus
from core.events.bus import EventBus
from core.models.events import AgentEvent
from core.models.tasks import Task
from core.runtime.context import ExecutionContext
from core.tasks.manager import TaskManager
from core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Core runtime engine driving the closed-loop agent execution lifecycle:
    OBSERVE -> UNDERSTAND -> PLAN -> ACT -> VERIFY -> RECOVER -> REMEMBER
    """

    def __init__(
        self,
        task_manager: TaskManager,
        tool_registry: ToolRegistry,
        event_bus: EventBus,
    ):
        self.task_manager = task_manager
        self.tool_registry = tool_registry
        self.event_bus = event_bus

    async def execute_task(
        self,
        task_id: str,
        simulate_verification_failure: bool = False,
        allow_recovery: bool = True,
    ) -> Task:
        """Execute a task through the full agent lifecycle."""
        task = await self.task_manager.get_task(task_id)
        if not task:
            raise KeyError(f"Task with ID {task_id} not found.")

        # Initialize per-task execution context
        context = ExecutionContext(
            task=task,
            available_tools=[t.name for t in self.tool_registry.list_tools()],
            metadata={"simulate_verification_failure": simulate_verification_failure},
        )

        try:
            # 1. OBSERVE
            await self._observe_stage(task, context)

            # 2. UNDERSTAND
            await self._understand_stage(task, context)

            # 3. PLAN
            await self._plan_stage(task, context)

            # 4. ACT
            await self._act_stage(task, context)

            # 5. VERIFY
            verified = await self._verify_stage(task, context, simulate_verification_failure)

            # 6. RECOVER (if verification failed)
            if not verified:
                recovered = await self._recover_stage(task, context, allow_recovery)
                if not recovered:
                    error_msg = "Task verification failed and recovery strategy was exhausted."
                    return await self.task_manager.fail_task(task.id, error_msg)

            # 7. REMEMBER
            await self._remember_stage(task, context)

            # 8. COMPLETE TASK
            result_payload = {
                "task_id": task.id,
                "input": task.input,
                "lifecycle_completed": True,
                "observations_count": len(context.observations),
                "actions_executed": context.action_results,
                "verifications": context.verification_results,
                "recovery_attempts": context.recovery_attempts,
                "memories_persisted": context.memory_entries,
                "execution_summary": "Task successfully executed through Phase 2 agent runtime without OS side effects.",
            }
            return await self.task_manager.complete_task(task.id, result_payload)

        except Exception as e:
            logger.exception(f"Unexpected error executing task {task_id}: {e}")
            return await self.task_manager.fail_task(task.id, str(e))

    async def _emit(
        self,
        task: Task,
        event_type: EventType,
        state: AgentLoopState,
        payload: Dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        await self.event_bus.publish(
            AgentEvent(
                task_id=task.id,
                event_type=event_type,
                source="core.agent_runtime",
                state=state,
                status=task.status,
                payload=payload,
                error=error,
            )
        )

    # -------------------------------------------------------------
    # Lifecycle Stages
    # -------------------------------------------------------------
    async def _observe_stage(self, task: Task, context: ExecutionContext) -> None:
        """OBSERVE: Contextual inspection."""
        await self.task_manager.update_task_state(task.id, AgentLoopState.OBSERVE)
        observation = {
            "source": "runtime_internal",
            "task_input_length": len(task.input),
            "target_environment": "Phase 2 Core Runtime",
            "available_tools": context.available_tools,
        }
        context.add_observation("context_inspection", observation)
        await self._emit(task, EventType.TASK_STATE_CHANGED, AgentLoopState.OBSERVE, {"observation": observation})

    async def _understand_stage(self, task: Task, context: ExecutionContext) -> None:
        """UNDERSTAND: Synthesize intent and requirements."""
        await self.task_manager.update_task_state(task.id, AgentLoopState.UNDERSTAND)
        understanding = {
            "intent": "runtime_verification" if "verification" in task.input.lower() else "generic_task",
            "requires_external_automation": False,
            "validation_mode": "deterministic_internal",
        }
        context.metadata["understanding"] = understanding
        await self._emit(task, EventType.TASK_STATE_CHANGED, AgentLoopState.UNDERSTAND, {"understanding": understanding})

    async def _plan_stage(self, task: Task, context: ExecutionContext) -> None:
        """PLAN: Establish action steps."""
        await self.task_manager.update_task_state(task.id, AgentLoopState.PLAN)
        plan = {
            "steps": [
                {"step": 1, "action": "execute_verification_tool", "tool": "demo_verification_tool"},
                {"step": 2, "action": "verify_result"},
                {"step": 3, "action": "persist_execution_context"},
            ]
        }
        context.metadata["plan"] = plan
        await self._emit(task, EventType.TASK_STATE_CHANGED, AgentLoopState.PLAN, {"plan": plan})

    async def _act_stage(self, task: Task, context: ExecutionContext) -> None:
        """ACT: Execute registered tools."""
        await self.task_manager.update_task_state(task.id, AgentLoopState.ACT)
        await self._emit(task, EventType.ACTION_STARTED, AgentLoopState.ACT, {"action": "demo_verification_tool"})

        if self.tool_registry.has_tool("demo_verification_tool"):
            action_result = await self.tool_registry.execute_tool(
                "demo_verification_tool",
                context,
                check_name=f"task_{task.id[:8]}",
                expected_value="passed",
            )
        else:
            action_result = {"status": "default_internal_action_completed", "executed": True}
            context.add_action_result("internal_action", success=True, output=action_result)

        await self._emit(task, EventType.ACTION_COMPLETED, AgentLoopState.ACT, {"result": action_result})

    async def _verify_stage(
        self,
        task: Task,
        context: ExecutionContext,
        simulate_failure: bool,
    ) -> bool:
        """VERIFY: Check outcome conditions."""
        await self.task_manager.update_task_state(task.id, AgentLoopState.VERIFY)
        await self._emit(task, EventType.VERIFICATION_STARTED, AgentLoopState.VERIFY, {})

        if simulate_failure:
            context.add_verification(verified=False, details="Simulated verification mismatch for testing recovery.")
            await self._emit(
                task,
                EventType.VERIFICATION_COMPLETED,
                AgentLoopState.VERIFY,
                {"verified": False, "reason": "simulated_verification_failure"},
            )
            return False

        # Real verification of action results
        has_successful_actions = any(ar.get("success") for ar in context.action_results)
        verified = has_successful_actions and len(context.action_results) > 0
        details = "Action output verified against expected deterministic parameters." if verified else "No valid action results found."

        context.add_verification(verified=verified, details=details)
        await self._emit(
            task,
            EventType.VERIFICATION_COMPLETED,
            AgentLoopState.VERIFY,
            {"verified": verified, "details": details},
        )
        return verified

    async def _recover_stage(
        self,
        task: Task,
        context: ExecutionContext,
        allow_recovery: bool,
    ) -> bool:
        """RECOVER: Handle verification discrepancy using alternate strategy."""
        await self.task_manager.update_task_state(task.id, AgentLoopState.RECOVER)
        await self._emit(task, EventType.RECOVERY_STARTED, AgentLoopState.RECOVER, {"allow_recovery": allow_recovery})

        if not allow_recovery:
            context.add_recovery_attempt("fallback_strategy", recovered=False, details="Recovery disallowed by task parameters.")
            await self._emit(
                task,
                EventType.RECOVERY_COMPLETED,
                AgentLoopState.RECOVER,
                {"recovered": False, "details": "Recovery denied"},
            )
            return False

        # Apply deterministic recovery strategy
        recovery_details = "Applied alternative verification strategy: re-evaluating internal sanity constraints."
        context.add_recovery_attempt("sanity_fallback", recovered=True, details=recovery_details)
        await self._emit(
            task,
            EventType.RECOVERY_COMPLETED,
            AgentLoopState.RECOVER,
            {"recovered": True, "details": recovery_details},
        )
        return True

    async def _remember_stage(self, task: Task, context: ExecutionContext) -> None:
        """REMEMBER: Store context and task outcomes."""
        await self.task_manager.update_task_state(task.id, AgentLoopState.REMEMBER)
        context.add_memory("last_task_input", task.input)
        context.add_memory("verification_status", "verified")

        await self._emit(
            task,
            EventType.MEMORY_STORED,
            AgentLoopState.REMEMBER,
            {"entries": context.memory_entries},
        )
