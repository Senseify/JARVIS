"""Tests for ReasoningEngine, Conversational Context, and Control Loop."""

import pytest
from core.ai.context import ConversationContext
from core.ai.engine import ReasoningEngine
from core.ai.manager import ModelManager
from core.models.ai import ChatRequest, ModelRole
from core.planning.planner import AutonomousPlanner
from core.planning.recovery import RecoveryEngine
from core.security.policy import SecurityPolicyEngine


@pytest.mark.asyncio
async def test_reasoning_engine_pure_conversation():
    model_mgr = ModelManager()
    sec_policy = SecurityPolicyEngine()
    planner = AutonomousPlanner(security_policy=sec_policy)
    recovery = RecoveryEngine()

    engine = ReasoningEngine(
        model_manager=model_mgr,
        planner=planner,
        recovery_engine=recovery,
        security_policy=sec_policy,
    )

    req = ChatRequest(message="Who are you?", session_id="test_conv")
    resp = await engine.process_chat(req)

    assert resp.requires_action is False
    assert resp.plan_id is None
    assert len(resp.tool_calls) == 0
    assert "JARVIS" in resp.message


@pytest.mark.asyncio
async def test_reasoning_engine_desktop_action_execution():
    model_mgr = ModelManager()
    sec_policy = SecurityPolicyEngine()
    planner = AutonomousPlanner(security_policy=sec_policy)
    recovery = RecoveryEngine()

    engine = ReasoningEngine(
        model_manager=model_mgr,
        planner=planner,
        recovery_engine=recovery,
        security_policy=sec_policy,
    )

    req = ChatRequest(message="Open Notepad and type hello world", session_id="test_act")
    resp = await engine.process_chat(req)

    assert resp.requires_action is True
    assert resp.plan_id is not None
    assert len(resp.tool_calls) == 2
    assert "Successfully completed" in resp.message or "Launching" in resp.message


def test_conversational_context_followup_pronoun_resolution():
    ctx = ConversationContext(session_id="ctx_test")
    ctx.update_active_app("Notepad")

    resolved = ctx.resolve_followup_references("Type hello world into it")
    assert resolved == "Type hello world into Notepad"

    resolved_close = ctx.resolve_followup_references("Close it now")
    assert resolved_close == "Close Notepad now"


def test_conversational_context_bounded_history():
    ctx = ConversationContext(session_id="bound_test", max_turns=4)

    for i in range(10):
        ctx.add_message(ModelRole.USER, f"User message {i}")
        ctx.add_message(ModelRole.ASSISTANT, f"Assistant reply {i}")

    assert len(ctx.messages) <= 4
