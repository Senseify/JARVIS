"""Capability registry mapping capability names to validators, controllers, and action receipts."""

import asyncio
from datetime import datetime, timezone
import logging
import platform
import sys
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, Type
from pydantic import BaseModel, ValidationError

from windows_agent.automation.applications import (
    ApplicationController,
    AppLaunchParams,
)
from windows_agent.automation.keyboard import (
    KeyboardController,
    KeyboardHotkeyParams,
    KeyboardPressParams,
    KeyboardTypeParams,
)
from windows_agent.automation.mouse import (
    MouseClickParams,
    MouseController,
    MouseDoubleClickParams,
    MouseMoveParams,
)
from windows_agent.automation.receipt import ActionReceipt, ReceiptTracker
from windows_agent.automation.windows import (
    WindowController,
    WindowFocusParams,
    WindowListParams,
)
from windows_agent.observation.capture import ScreenCapture
from windows_agent.observation.models import (
    ActionVerifyParams,
    CaptureScreenParams,
    ScreenState,
    VerificationResult,
)
from windows_agent.observation.policy import (
    AdaptiveObservationPolicy,
    ObservationTrigger,
)
from windows_agent.observation.store import ObservationStore
from windows_agent.observation.verifier import VerificationEngine

logger = logging.getLogger(__name__)

CapabilityHandler = Callable[[Any], Coroutine[Any, Any, Dict[str, Any]]]


class CapabilityRegistry:
    """Registry maintaining authorized, validated machine-side capabilities with action receipts."""

    def __init__(
        self,
        agent_version: str = "0.1.0",
        start_time: Optional[float] = None,
        mouse_controller: Optional[MouseController] = None,
        keyboard_controller: Optional[KeyboardController] = None,
        window_controller: Optional[WindowController] = None,
        app_controller: Optional[ApplicationController] = None,
        observation_store: Optional[ObservationStore] = None,
        screen_capture: Optional[ScreenCapture] = None,
        verification_engine: Optional[VerificationEngine] = None,
        observation_policy: Optional[AdaptiveObservationPolicy] = None,
    ):
        self.agent_version = agent_version
        self.start_time = start_time or time.time()
        self._capabilities: Dict[str, Dict[str, Any]] = {}

        # Automation Controllers
        self.mouse = mouse_controller or MouseController()
        self.keyboard = keyboard_controller or KeyboardController()
        self.windows = window_controller or WindowController()
        self.apps = app_controller or ApplicationController()

        # Observation & Verification Subsystems
        self.store = observation_store or ObservationStore()
        self.capture = screen_capture or ScreenCapture(store=self.store)
        self.verifier = verification_engine or VerificationEngine()
        self.policy = observation_policy or AdaptiveObservationPolicy()

        self._register_all_capabilities()

    def register(
        self,
        name: str,
        handler: CapabilityHandler,
        description: str = "",
        validator_cls: Optional[Type[BaseModel]] = None,
    ) -> None:
        """Register a capability handler with an optional Pydantic validator schema."""
        self._capabilities[name] = {
            "handler": handler,
            "validator_cls": validator_cls,
            "description": description,
        }
        logger.info(f"Registered capability: {name}")

    def list_capabilities(self) -> List[str]:
        """List all supported capability names."""
        return sorted(list(self._capabilities.keys()))

    def has_capability(self, name: str) -> bool:
        """Check if capability is registered."""
        return name in self._capabilities

    def get_description(self, name: str) -> str:
        """Get capability description."""
        if name in self._capabilities:
            return self._capabilities[name]["description"]
        return ""

    async def execute(
        self,
        name: str,
        params: Dict[str, Any],
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate payload, execute capability, and return a structured action receipt."""
        if name not in self._capabilities:
            allowed = self.list_capabilities()
            raise KeyError(f"Unsupported capability: '{name}'. Supported: {allowed}")

        entry = self._capabilities[name]
        handler = entry["handler"]
        validator_cls = entry["validator_cls"]

        # Validate input parameters if a schema is registered
        if validator_cls is not None:
            try:
                validated_params = validator_cls.model_validate(params)
            except ValidationError as e:
                raise ValueError(f"Invalid parameters for capability '{name}': {e}")
        else:
            validated_params = params

        # Execute under ReceiptTracker to record precise start/end and duration
        tracker = ReceiptTracker(capability=name, request_id=request_id)
        with tracker:
            try:
                raw_result = await handler(validated_params)
                is_success = True
                if isinstance(raw_result, dict) and raw_result.get("success") is False:
                    is_success = False
                receipt = tracker.create_receipt(success=is_success, result=raw_result)
                receipt_dict = receipt.model_dump()
                # Merge top-level result keys for convenient direct access
                if isinstance(raw_result, dict):
                    for k, v in raw_result.items():
                        receipt_dict[k] = v
                return receipt_dict
            except Exception as e:
                receipt = tracker.create_receipt(success=False, error=str(e))
                raise RuntimeError(str(e)) from e

    def _register_all_capabilities(self) -> None:
        """Register diagnostic, automation, observation, and verification capabilities."""

        # -------------------------------------------------------------
        # 1. Diagnostic / System Capabilities
        # -------------------------------------------------------------
        async def ping_handler(params: Any) -> Dict[str, Any]:
            return {
                "pong": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_version": self.agent_version,
            }

        async def system_info_handler(params: Any) -> Dict[str, Any]:
            return {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "hostname": platform.node(),
                "python_version": platform.python_version(),
                "agent_version": self.agent_version,
                "is_windows": sys.platform == "win32",
            }

        async def agent_status_handler(params: Any) -> Dict[str, Any]:
            uptime = time.time() - self.start_time
            return {
                "status": "online",
                "uptime_seconds": round(uptime, 2),
                "agent_version": self.agent_version,
                "registered_capabilities": self.list_capabilities(),
            }

        self.register("agent.ping", ping_handler, description="Heartbeat pong response.")
        self.register("system.info", system_info_handler, description="Host platform and environment info.")
        self.register("agent.status", agent_status_handler, description="Agent uptime and capabilities status.")

        # -------------------------------------------------------------
        # 2. Mouse Capabilities
        # -------------------------------------------------------------
        self.register(
            "mouse.move",
            self.mouse.move,
            description="Move mouse cursor to target screen coordinates.",
            validator_cls=MouseMoveParams,
        )
        self.register(
            "mouse.click",
            self.mouse.click,
            description="Click mouse button at current or specified coordinates.",
            validator_cls=MouseClickParams,
        )
        self.register(
            "mouse.double_click",
            self.mouse.double_click,
            description="Double-click mouse button at current or specified coordinates.",
            validator_cls=MouseDoubleClickParams,
        )

        # -------------------------------------------------------------
        # 3. Keyboard Capabilities
        # -------------------------------------------------------------
        self.register(
            "keyboard.type",
            self.keyboard.type,
            description="Type a sequence of characters.",
            validator_cls=KeyboardTypeParams,
        )
        self.register(
            "keyboard.press",
            self.keyboard.press,
            description="Press a single key (e.g. enter, tab, esc).",
            validator_cls=KeyboardPressParams,
        )
        self.register(
            "keyboard.hotkey",
            self.keyboard.hotkey,
            description="Press a key combination (e.g. ['ctrl', 'c']).",
            validator_cls=KeyboardHotkeyParams,
        )

        # -------------------------------------------------------------
        # 4. Window Capabilities
        # -------------------------------------------------------------
        self.register(
            "window.list",
            self.windows.list_windows,
            description="List running top-level windows.",
            validator_cls=WindowListParams,
        )
        self.register(
            "window.focus",
            self.windows.focus,
            description="Bring target window to foreground by handle or title.",
            validator_cls=WindowFocusParams,
        )

        # -------------------------------------------------------------
        # 5. Application Capabilities
        # -------------------------------------------------------------
        self.register(
            "app.launch",
            self.apps.launch,
            description="Launch an allowlisted desktop application.",
            validator_cls=AppLaunchParams,
        )

        # -------------------------------------------------------------
        # 6. Screen Observation Capability (Phase 5)
        # -------------------------------------------------------------
        async def screen_capture_handler(params: CaptureScreenParams) -> Dict[str, Any]:
            state = await self.capture.capture(params)
            return state.model_dump()

        self.register(
            "screen.capture",
            screen_capture_handler,
            description="Perform a request-driven screen capture and return structured metadata.",
            validator_cls=CaptureScreenParams,
        )

        # -------------------------------------------------------------
        # 7. Action -> Observe -> Verify Capability (Phase 5)
        # -------------------------------------------------------------
        async def action_verify_handler(params: ActionVerifyParams) -> Dict[str, Any]:
            pre_state_dict = None
            if self.policy.should_observe(ObservationTrigger.BEFORE_ACTION, require_pre_observe=params.pre_observe):
                pre_state = await self.capture.capture()
                pre_state_dict = pre_state.model_dump()

            # Execute the action capability
            action_receipt = await self.execute(params.action_capability, params.action_parameters)

            # Brief pause for window creation if applicable
            if params.action_capability in ("app.launch", "window.focus"):
                await asyncio.sleep(0.3)

            # Post-action screen observation
            post_state = await self.capture.capture()

            # Enumerate windows if verifying window properties
            win_result = await self.windows.list_windows(WindowListParams(include_invisible=False))
            window_list = win_result.get("windows", [])

            # Run deterministic verification check
            verification_res = self.verifier.verify_condition(
                condition=params.expected_condition,
                expected_value=params.expected_value,
                screen_state=post_state,
                window_list=window_list,
            )

            return {
                "action_capability": params.action_capability,
                "action_receipt": action_receipt,
                "verified": verification_res.passed,
                "verification": verification_res.model_dump(),
                "post_screen_state": post_state.model_dump(),
                "pre_screen_state": pre_state_dict,
                "success": bool(action_receipt.get("success", False) and verification_res.passed),
                "failure_reason": verification_res.failure_reason,
            }

        self.register(
            "action.verify",
            action_verify_handler,
            description="Execute an action capability, observe resulting state, and verify expected condition.",
            validator_cls=ActionVerifyParams,
        )
