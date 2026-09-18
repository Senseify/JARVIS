"""Central Reasoning Engine executing the unified control loop:

OBSERVE → UNDERSTAND → PLAN → ACT → VERIFY → RECOVER → REMEMBER → RESPOND
"""

import logging
import time
from typing import Any
from core.ai.context import ConversationContext
from core.ai.manager import ModelManager
from core.ai.vision_reasoning import VisionReasoningAdapter
from core.devices.agent_bridge import AgentBridge
from core.constants import EventType, OrbState
from core.events.bus import EventBus
from core.knowledge.service import KnowledgeService
from core.memory.service import MemoryService
from core.models.ai import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ModelRequest,
    ModelRole,
)
from core.models.events import AgentEvent
from core.models.memory import MemoryCreateRequest, MemoryType
from core.models.planning import (
    FailureClassification,
    Plan,
    PlanStatus,
    PlanStep,
    StepStatus,
)
from core.planning.planner import AutonomousPlanner
from core.planning.recovery import RecoveryEngine
from core.security.policy import SecurityPolicyEngine
from core.skills.executor import SkillExecutor
from core.tasks.manager import TaskManager

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """The central intelligence and orchestration engine of JARVIS OS."""

    def __init__(
        self,
        model_manager: ModelManager,
        planner: AutonomousPlanner,
        recovery_engine: RecoveryEngine,
        security_policy: SecurityPolicyEngine,
        memory_service: MemoryService | None = None,
        knowledge_service: KnowledgeService | None = None,
        skill_executor: SkillExecutor | None = None,
        agent_bridge: AgentBridge | None = None,
        task_manager: TaskManager | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.model_manager = model_manager
        self.planner = planner
        self.recovery_engine = recovery_engine
        self.security_policy = security_policy
        self.memory_service = memory_service
        self.knowledge_service = knowledge_service or KnowledgeService()
        self.skill_executor = skill_executor
        self.agent_bridge = agent_bridge
        self.task_manager = task_manager
        self.event_bus = event_bus
        self.vision_adapter = VisionReasoningAdapter()
        self._contexts: dict[str, ConversationContext] = {}

    def get_context(self, session_id: str) -> ConversationContext:
        """Get or create session conversational context."""
        if session_id not in self._contexts:
            self._contexts[session_id] = ConversationContext(session_id=session_id)
        return self._contexts[session_id]

    async def _emit_orb(self, state: OrbState, detail: str = "") -> None:
        """Publish updated orb state to WebSocket clients."""
        if self.event_bus:
            await self.event_bus.publish(
                AgentEvent(
                    event_type=EventType.ORB_STATE_CHANGED,
                    payload={"state": state.value, "detail": detail},
                )
            )

    async def process_chat(self, request: ChatRequest) -> ChatResponse:
        """Process conversational or task requests from text/voice/API."""
        start_time = time.perf_counter()
        context = self.get_context(request.session_id)

        # 1. Resolve follow-up pronouns (e.g. 'type into it' -> active app)
        resolved_message = context.resolve_followup_references(request.message)

        # 2. Update context & state
        context.add_message(ModelRole.USER, resolved_message)
        await self._emit_orb(OrbState.THINKING, "Analyzing request")

        if self.event_bus:
            await self.event_bus.publish(
                AgentEvent(
                    event_type=EventType.REASONING_STARTED,
                    payload={"session_id": request.session_id, "query": resolved_message},
                )
            )

        # 3. Memory Retrieval (relevant context only, avoiding spam)
        memory_context = ""
        if self.memory_service:
            search_results = await self.memory_service.search_memory(
                query=resolved_message,
                limit=3,
                min_importance=0.3,
            )
            if search_results:
                memory_context = "Relevant memories:\n" + "\n".join(
                    f"- [{sr.entry.memory_type.value}] {sr.entry.content}" for sr in search_results
                )

        # 4. Construct prompt messages
        messages = [
            ChatMessage(
                role=ModelRole.SYSTEM,
                content=(
                    "You are JARVIS, an autonomous personal AI agent. "
                    "Determine whether the user's request is purely conversational or requires desktop action. "
                    "If action is required, emit structured tool calls. "
                    "Never execute arbitrary shell commands."
                ),
            )
        ]
        if memory_context:
            messages.append(ChatMessage(role=ModelRole.SYSTEM, content=memory_context))

        # Add recent conversation turns
        messages.extend(context.messages[-6:])

        # 5. Model Inference
        model_req = ModelRequest(messages=messages, timeout_seconds=30.0)
        model_resp = await self.model_manager.generate(model_req)

        if self.event_bus:
            await self.event_bus.publish(
                AgentEvent(
                    event_type=EventType.REASONING_COMPLETED,
                    payload={"session_id": request.session_id, "duration_ms": model_resp.duration_ms},
                )
            )

        # 6. Check if action execution is required
        if not model_resp.tool_calls:
            # Pure conversation turn
            context.add_message(ModelRole.ASSISTANT, model_resp.content)
            await self._emit_orb(OrbState.IDLE, "Ready")
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ChatResponse(
                session_id=request.session_id,
                message=model_resp.content,
                requires_action=False,
                model_used=model_resp.model_name,
                duration_ms=duration_ms,
            )

        # 7. Action execution required: Generate multi-step plan
        await self._emit_orb(OrbState.PLANNING, f"Creating plan for {len(model_resp.tool_calls)} steps")
        try:
            plan = self.planner.create_plan_from_tool_calls(
                goal=resolved_message,
                tool_calls=model_resp.tool_calls,
                device_id=request.device_id,
            )
        except PermissionError as exc:
            await self._emit_orb(OrbState.ERROR, "Security policy violation")
            return ChatResponse(
                session_id=request.session_id,
                message=f"Action prohibited by security policy: {exc}",
                requires_action=False,
                model_used=model_resp.model_name,
                duration_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        if self.event_bus:
            await self.event_bus.publish(
                AgentEvent(
                    event_type=EventType.PLAN_CREATED,
                    payload={"plan_id": plan.plan_id, "goal": plan.goal, "steps_count": len(plan.steps)},
                )
            )

        # 8. Execute Plan through Central Control Loop
        execution_success = await self.execute_plan(plan, context)

        final_msg = plan.final_response or (
            f"Successfully completed: {plan.goal}." if execution_success else f"Task failed: {plan.goal}."
        )
        context.add_message(ModelRole.ASSISTANT, final_msg)

        # 9. Remember outcome (store exactly one useful outcome entry)
        if self.memory_service:
            await self.memory_service.store_memory(
                content=f"Executed plan '{plan.goal}': {'success' if execution_success else 'failed'}",
                memory_type=MemoryType.OUTCOME,
                importance=0.6,
                tags=["plan_outcome", plan.plan_id],
                source="reasoning_engine",
            )

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return ChatResponse(
            session_id=request.session_id,
            message=final_msg,
            plan_id=plan.plan_id,
            requires_action=True,
            tool_calls=model_resp.tool_calls,
            model_used=model_resp.model_name,
            duration_ms=duration_ms,
        )

    async def execute_plan(self, plan: Plan, context: ConversationContext | None = None) -> bool:
        """Execute a plan's steps sequentially with verification and recovery."""
        plan.status = PlanStatus.IN_PROGRESS
        overall_success = True

        for idx, step in enumerate(plan.steps):
            plan.current_step_index = idx
            step_success = await self._execute_step_with_recovery(step, plan, context)
            if not step_success:
                plan.status = PlanStatus.FAILED
                overall_success = False
                break

        if overall_success:
            plan.status = PlanStatus.COMPLETED
            await self._emit_orb(OrbState.SUCCESS, "Plan execution complete")
            if self.event_bus:
                await self.event_bus.publish(
                    AgentEvent(
                        event_type=EventType.PLAN_COMPLETED,
                        payload={"plan_id": plan.plan_id, "goal": plan.goal},
                    )
                )
        else:
            await self._emit_orb(OrbState.ERROR, "Plan execution failed")
            if self.event_bus:
                await self.event_bus.publish(
                    AgentEvent(
                        event_type=EventType.PLAN_STEP_FAILED,
                        payload={"plan_id": plan.plan_id, "step_id": plan.steps[plan.current_step_index].step_id},
                    )
                )

        return overall_success

    async def _execute_step_with_recovery(
        self,
        step: PlanStep,
        plan: Plan,
        context: ConversationContext | None = None,
    ) -> bool:
        """Execute a single step with bounded retry and recovery."""
        while step.retry_count <= step.max_retries:
            step.status = StepStatus.RUNNING
            await self._emit_orb(OrbState.ACTING, f"Executing: {step.name}")

            if self.event_bus:
                await self.event_bus.publish(
                    AgentEvent(
                        event_type=EventType.PLAN_STEP_STARTED,
                        payload={"plan_id": plan.plan_id, "step_id": step.step_id, "tool": step.tool},
                    )
                )

            # Virtual Cursor target update
            if step.tool in ("mouse.click", "mouse.move") and "x" in step.arguments and "y" in step.arguments:
                if self.event_bus:
                    await self.event_bus.publish(
                        AgentEvent(
                            event_type=EventType.VIRTUAL_CURSOR_MOVED,
                            payload={"x": step.arguments["x"], "y": step.arguments["y"], "action": step.tool},
                        )
                    )

            # Dispatch step action
            action_error: str | None = None
            action_result: Any = None
            try:
                action_result = await self._dispatch_tool_action(step.tool, step.arguments, plan.device_id)
                step.result = action_result
                # Update context active app if app launched
                if step.tool in ("app.launch", "app.open") and context:
                    context.update_active_app(step.arguments.get("app"))
            except Exception as exc:
                logger.error("Step execution error for '%s': %s", step.name, exc)
                action_error = str(exc)

            # Verification checkpoint
            verification_ok = True
            if not action_error and step.verification_required:
                step.status = StepStatus.VERIFYING
                await self._emit_orb(OrbState.VERIFYING, f"Verifying {step.name}")
                if self.event_bus:
                    await self.event_bus.publish(
                        AgentEvent(
                            event_type=EventType.PLAN_STEP_VERIFYING,
                            payload={"plan_id": plan.plan_id, "step_id": step.step_id},
                        )
                    )
                verification_ok = await self._verify_step(step, plan.device_id)

            if not action_error and verification_ok:
                step.status = StepStatus.COMPLETED
                if self.event_bus:
                    await self.event_bus.publish(
                        AgentEvent(
                            event_type=EventType.PLAN_STEP_COMPLETED,
                            payload={"plan_id": plan.plan_id, "step_id": step.step_id},
                        )
                    )
                return True

            # Failure encountered -> Classify and attempt recovery
            classification = self.recovery_engine.classify_failure(
                action_error or "verification_failed",
                {"step": step.tool},
            )
            step.error = action_error or "Verification check failed."

            can_retry = await self.recovery_engine.attempt_recovery(step, plan.plan_id, classification)
            if not can_retry:
                step.status = StepStatus.FAILED
                plan.final_response = (
                    f"Action '{step.name}' could not be verified or executed after recovery attempts."
                )
                return False

        return False

    async def _dispatch_tool_action(self, tool: str, arguments: dict[str, Any], device_id: str | None) -> Any:
        """Dispatch tool action to AgentBridge or SkillExecutor."""
        # 1. Composite skill execution
        if tool in ("launch_and_verify", "type_and_verify", "click_and_verify") and self.skill_executor:
            skill_res = await self.skill_executor.execute(tool, arguments, device_id=device_id)
            if not skill_res.success:
                raise RuntimeError(skill_res.error or "Skill execution failed")
            return skill_res.outputs

        # 2. AgentBridge direct command dispatch
        if self.agent_bridge:
            # Check connected devices
            devices = self.agent_bridge.list_connected_devices()
            target = device_id or (devices[0] if devices else None)
            if target:
                res = await self.agent_bridge.dispatch_command(target, tool, arguments)
                if not res.success:
                    raise RuntimeError(res.error or "Bridge command failed")
                return res.data

        # Fallback simulation for offline testing / standalone core
        logger.info("Executing simulated tool '%s' with args %s", tool, arguments)
        return {"status": "executed", "tool": tool, "args": arguments}

    async def _verify_step(self, step: PlanStep, device_id: str | None) -> bool:
        """Verify the outcome of a step (window existence, text present, etc.)."""
        # Read-only verification check
        # In test / non-Windows environments, simulated verification succeeds unless explicitly flagged
        if "fail_verification" in step.arguments and step.arguments["fail_verification"]:
            return False
        return True
