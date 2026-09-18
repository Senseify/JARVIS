"""Tests for centralized SecurityPolicyEngine and action evaluation."""

import pytest
from core.models.security import RiskLevel, SecurityPolicyConfig
from core.security.policy import SecurityPolicyEngine


def test_allowlisted_application_launch():
    engine = SecurityPolicyEngine()
    eval_res = engine.evaluate("app.launch", {"app": "notepad"})
    assert eval_res.allowed is True
    assert eval_res.risk_level == RiskLevel.LOW_RISK
    assert "allowlisted" in eval_res.reason.lower()


def test_non_allowlisted_application_blocked():
    engine = SecurityPolicyEngine()
    eval_res = engine.evaluate("app.launch", {"app": "unauthorized_malware.exe"})
    assert eval_res.allowed is False
    assert eval_res.risk_level == RiskLevel.BLOCKED
    assert "not in the approved allowlist" in eval_res.reason


def test_arbitrary_shell_and_code_execution_blocked():
    engine = SecurityPolicyEngine()

    blocked_tools = [
        "shell.execute",
        "cmd.run",
        "powershell.run",
        "eval",
        "system.exec",
        "bash.exec",
        "custom_shell_tool",
    ]
    for tool in blocked_tools:
        eval_res = engine.evaluate(tool, {"cmd": "dir"})
        assert eval_res.allowed is False
        assert eval_res.risk_level == RiskLevel.BLOCKED


def test_input_automation_validation():
    engine = SecurityPolicyEngine(SecurityPolicyConfig(max_typing_length=100))

    # Normal typing
    eval_ok = engine.evaluate("keyboard.type", {"text": "hello world"})
    assert eval_ok.allowed is True
    assert eval_ok.risk_level == RiskLevel.MEDIUM_RISK

    # Excessive typing length
    eval_long = engine.evaluate("keyboard.type", {"text": "A" * 200})
    assert eval_long.allowed is False
    assert eval_long.risk_level == RiskLevel.BLOCKED

    # Mouse clicks
    eval_click = engine.evaluate("mouse.click", {"button": "left"})
    assert eval_click.allowed is True
    assert eval_click.risk_level == RiskLevel.MEDIUM_RISK


def test_read_only_observation_tools():
    engine = SecurityPolicyEngine()

    read_tools = [
        "screen.capture",
        "screen.ocr",
        "screen.ui_detect",
        "window.list",
        "window.focus",
        "action.verify",
    ]
    for tool in read_tools:
        eval_res = engine.evaluate(tool, {})
        assert eval_res.allowed is True
        assert eval_res.risk_level == RiskLevel.READ_ONLY


def test_unrecognized_tool_default_deny():
    engine = SecurityPolicyEngine()
    eval_res = engine.evaluate("unknown.random.tool", {"foo": "bar"})
    assert eval_res.allowed is False
    assert eval_res.risk_level == RiskLevel.BLOCKED
