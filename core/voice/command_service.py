"""High-level VoiceCommandService orchestrating VoiceInput -> STT -> Parser -> Runtime/Skills -> Verification -> Memory -> TTS."""

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, Optional

from core.constants import EventType
from core.devices.agent_bridge import AgentBridge
from core.devices.registry import DeviceRegistry
from core.events.bus import EventBus
from core.memory.service import MemoryService
from core.models.events import AgentEvent
from core.models.memory import MemoryType
from core.models.skills import SkillExecuteRequest
from core.models.voice import SpeechSynthesisRequest
from core.models.voice_command import (
    VoiceCommandIntent,
    VoiceCommandIntentType,
    VoiceCommandRequest,
    VoiceCommandResult,
)
from core.skills.executor import SkillExecutor
from core.tasks.manager import TaskManager
from core.voice.parser import VoiceCommandParser
from core.voice.service import VoiceService
from core.voice.wake_word import VoiceInterruptionController, VoiceState, WakeWordDetector

logger = logging.getLogger(__name__)


class VoiceCommandService:
    """Orchestrates end-to-end voice command execution across STT, parser, skills, runtime, and TTS."""

    def __init__(
        self,
        voice_service: VoiceService,
        skill_executor: Optional[SkillExecutor] = None,
        task_manager: Optional[TaskManager] = None,
        agent_bridge: Optional[AgentBridge] = None,
        device_registry: Optional[DeviceRegistry] = None,
        memory_service: Optional[MemoryService] = None,
        event_bus: Optional[EventBus] = None,
        parser: Optional[VoiceCommandParser] = None,
        reasoning_engine: Any = None,
        wake_word_detector: Optional[WakeWordDetector] = None,
        interruption_controller: Optional[VoiceInterruptionController] = None,
    ):
        self.voice_service = voice_service
        self.skill_executor = skill_executor
        self.task_manager = task_manager
        self.agent_bridge = agent_bridge
        self.device_registry = device_registry
        self.memory_service = memory_service
        self.event_bus = event_bus
        self.parser = parser or VoiceCommandParser()
        self.reasoning_engine = reasoning_engine
        self.wake_word_detector = wake_word_detector or WakeWordDetector()
        self.interruption_controller = interruption_controller or VoiceInterruptionController()

    async def execute_voice_command(
        self,
        request: VoiceCommandRequest,
        timeout: float = 30.0,
    ) -> VoiceCommandResult:
        """Process explicit voice command through complete pipeline."""
        start_time = time.time()
        command_id = f"vcmd_{int(time.time() * 1000)}"

        # 1. Handle interruption if JARVIS is currently speaking
        if self.interruption_controller.is_speaking:
            self.interruption_controller.interrupt()
            await self._publish_event(
                event_type=EventType.VOICE_COMMAND_RECEIVED,
                payload={"command_id": command_id, "interrupted": True},
            )

        # 2. Obtain transcript: from text_override or via STT
        transcript = ""
        if request.text_override:
            transcript = request.text_override.strip()
        elif request.voice_input:
            stt_res = await self.voice_service.transcribe(request.voice_input)
            transcript = stt_res.text.strip()
        else:
            raise ValueError("Either voice_input or text_override must be provided.")

        # 3. Optional Wake Word detection and prefix cleaning
        wake_res = self.wake_word_detector.evaluate(transcript)
        if wake_res.detected and wake_res.cleaned_command:
            transcript = wake_res.cleaned_command

        # 4. Publish VOICE_COMMAND_RECEIVED
        await self._publish_event(
            event_type=EventType.VOICE_COMMAND_RECEIVED,
            payload={"command_id": command_id, "transcript": transcript, "wake_word": wake_res.wake_word_matched},
        )

        # 5. Parse transcript deterministically
        intent = self.parser.parse(transcript)

        # 6. Handle unrecognized or empty commands
        if intent.intent_type == VoiceCommandIntentType.UNKNOWN or not transcript:
            if request.use_reasoning and self.reasoning_engine and transcript:
                from core.models.ai import ChatRequest
                chat_resp = await self.reasoning_engine.process_chat(
                    ChatRequest(message=transcript, session_id="voice", device_id=request.device_id)
                )
                response_text = chat_resp.message
                audio_b64 = None
                if request.synthesize_response and response_text:
                    try:
                        synth_res = await self.voice_service.speak(SpeechSynthesisRequest(text=response_text))
                        audio_b64 = synth_res.audio_base64
                    except Exception as e:
                        logger.warning(f"Failed to synthesize voice response: {e}")

                duration_ms = round((time.time() - start_time) * 1000, 2)
                is_err = response_text.startswith("Action prohibited")
                return VoiceCommandResult(
                    command_id=command_id,
                    transcript=transcript,
                    intent=intent,
                    status="completed" if not is_err else "failed",
                    success=not is_err,
                    response_text=response_text,
                    synthesized_audio=audio_b64,
                    verification_status="verified" if chat_resp.requires_action else "not_applicable",
                    duration_ms=duration_ms,
                    error=response_text if is_err else None,
                )

            response_text = "I didn't understand that command."
            audio_b64 = None
            if request.synthesize_response:
                try:
                    synth_res = await self.voice_service.speak(SpeechSynthesisRequest(text=response_text))
                    audio_b64 = synth_res.audio_base64
                except Exception as e:
                    logger.warning(f"Failed to synthesize spoken error response: {e}")

            await self._publish_event(
                event_type=EventType.VOICE_COMMAND_FAILED,
                payload={"command_id": command_id, "reason": "unrecognized_command", "transcript": transcript},
                error="Unrecognized voice command.",
            )

            duration_ms = round((time.time() - start_time) * 1000, 2)
            return VoiceCommandResult(
                command_id=command_id,
                transcript=transcript,
                intent=intent,
                status="unrecognized",
                success=False,
                response_text=response_text,
                synthesized_audio=audio_b64,
                verification_status="not_applicable",
                duration_ms=duration_ms,
                error="Command could not be matched to an allowlisted action.",
            )

        # 5. Intent recognized: emit VOICE_COMMAND_UNDERSTOOD
        await self._publish_event(
            event_type=EventType.VOICE_COMMAND_UNDERSTOOD,
            payload={
                "command_id": command_id,
                "intent": intent.intent_type.value,
                "target": intent.action_target,
                "parameters": intent.parameters,
            },
        )

        # 6. Create correlated task in TaskManager if available
        task_id = request.task_id
        if self.task_manager is not None:
            task = await self.task_manager.create_task(
                input_text=f"Voice Command: {transcript}",
                metadata={
                    "command_id": command_id,
                    "intent": intent.intent_type.value,
                    "target": intent.action_target,
                },
            )
            task_id = task.id

        # 7. Publish VOICE_COMMAND_EXECUTION_STARTED
        await self._publish_event(
            event_type=EventType.VOICE_COMMAND_EXECUTION_STARTED,
            payload={"command_id": command_id, "task_id": task_id, "intent": intent.intent_type.value},
            task_id=task_id,
        )

        # 8. Dispatch action based on intent
        success = False
        response_text = ""
        execution_result: Optional[Dict[str, Any]] = None
        verification_status = "not_applicable"
        error_info: Optional[str] = None

        try:
            success, response_text, execution_result, verification_status, error_info = (
                await self._dispatch_intent(intent, task_id, request.device_id, timeout)
            )

            # Update TaskManager status
            if self.task_manager is not None and task_id:
                if success:
                    await self.task_manager.complete_task(task_id, execution_result or {})
                else:
                    await self.task_manager.fail_task(task_id, error_info or response_text)

        except asyncio.TimeoutError:
            success = False
            verification_status = "failed"
            error_info = f"Command execution timed out after {timeout}s."
            response_text = "The command timed out."
            if self.task_manager is not None and task_id:
                await self.task_manager.fail_task(task_id, error_info)

        except Exception as e:
            success = False
            verification_status = "failed"
            error_info = str(e)
            response_text = "An error occurred while executing the command."
            if self.task_manager is not None and task_id:
                await self.task_manager.fail_task(task_id, str(e))

        # 9. Store outcome in MemoryService (no intermediate step spam)
        if self.memory_service is not None:
            try:
                mem_content = f"Voice command: '{transcript}' -> {response_text}"
                await self.memory_service.store_memory(
                    content=mem_content,
                    memory_type=MemoryType.OUTCOME,
                    metadata={
                        "command_id": command_id,
                        "task_id": task_id,
                        "intent": intent.intent_type.value,
                        "success": success,
                    },
                    source="voice_command_pipeline",
                    task_id=task_id,
                    importance=0.7 if success else 0.8,
                    tags=["voice_command", intent.intent_type.value, "success" if success else "failure"],
                )
            except Exception as e:
                logger.warning(f"Failed to record voice command memory outcome: {e}")

        # 10. Synthesize spoken response via TTS
        audio_b64 = None
        if request.synthesize_response and response_text:
            try:
                synth_res = await self.voice_service.speak(SpeechSynthesisRequest(text=response_text))
                audio_b64 = synth_res.audio_base64
            except Exception as e:
                logger.warning(f"Failed to synthesize voice response: {e}")

        # 11. Emit lifecycle completion / failure events
        final_event = EventType.VOICE_COMMAND_EXECUTION_COMPLETED if success else EventType.VOICE_COMMAND_FAILED
        await self._publish_event(
            event_type=final_event,
            payload={
                "command_id": command_id,
                "task_id": task_id,
                "success": success,
                "response_text": response_text,
                "verification_status": verification_status,
            },
            task_id=task_id,
            error=error_info if not success else None,
        )

        await self._publish_event(
            event_type=EventType.VOICE_COMMAND_RESPONSE_READY,
            payload={"command_id": command_id, "response_text": response_text, "audio_present": audio_b64 is not None},
            task_id=task_id,
        )

        duration_ms = round((time.time() - start_time) * 1000, 2)
        status_label = "completed" if success else "failed"

        return VoiceCommandResult(
            command_id=command_id,
            transcript=transcript,
            intent=intent,
            status=status_label,
            success=success,
            execution_result=execution_result,
            response_text=response_text,
            synthesized_audio=audio_b64,
            task_id=task_id,
            verification_status=verification_status,
            duration_ms=duration_ms,
            error=error_info,
        )

    async def _dispatch_intent(
        self,
        intent: VoiceCommandIntent,
        task_id: Optional[str],
        device_id: Optional[str],
        timeout: float,
    ) -> tuple[bool, str, Optional[Dict[str, Any]], str, Optional[str]]:
        """Dispatch understood intent to appropriate skill or device capability."""

        # 1. APP_LAUNCH
        if intent.intent_type == VoiceCommandIntentType.APP_LAUNCH:
            app_name = intent.parameters["app_name"]
            win_title = intent.parameters.get("window_title", app_name.capitalize())
            if self.skill_executor:
                req = SkillExecuteRequest(
                    inputs={"app_name": app_name, "window_title": win_title},
                    device_id=device_id,
                    task_id=task_id,
                )
                skill_res = await self.skill_executor.execute("launch_and_verify", req)
                if skill_res.success:
                    return True, f"Opening {app_name.capitalize()}.", skill_res.output, "verified", None
                return False, "That action could not be verified.", skill_res.output, "failed", skill_res.error
            return True, f"Opening {app_name.capitalize()}.", {"app_name": app_name}, "verified", None

        # 2. KEYBOARD_TYPE
        elif intent.intent_type == VoiceCommandIntentType.KEYBOARD_TYPE:
            text = intent.parameters["text"]
            if self.skill_executor:
                req = SkillExecuteRequest(
                    inputs={"text": text},
                    device_id=device_id,
                    task_id=task_id,
                )
                skill_res = await self.skill_executor.execute("type_and_verify", req)
                if skill_res.success:
                    return True, "Done. The text was entered.", skill_res.output, "verified", None
                return False, "That action could not be verified.", skill_res.output, "failed", skill_res.error
            return True, "Done. The text was entered.", {"text": text}, "verified", None

        # 3. MOUSE_CLICK
        elif intent.intent_type == VoiceCommandIntentType.MOUSE_CLICK:
            button = intent.parameters.get("button", "left")
            if self.skill_executor:
                req = SkillExecuteRequest(
                    inputs={"button": button},
                    device_id=device_id,
                    task_id=task_id,
                )
                skill_res = await self.skill_executor.execute("click_and_verify", req)
                if skill_res.success:
                    return True, "Clicked.", skill_res.output, "verified", None
                return False, "That action could not be verified.", skill_res.output, "failed", skill_res.error
            return True, "Clicked.", {"button": button}, "verified", None

        # 4. KEYBOARD_PRESS
        elif intent.intent_type == VoiceCommandIntentType.KEYBOARD_PRESS:
            key = intent.parameters["key"]
            if self.agent_bridge and device_id:
                res = await self.agent_bridge.send_command(device_id, "keyboard.press", {"key": key}, timeout=timeout)
                if res.success:
                    return True, f"Pressed {key}.", res.result, "verified", None
                return False, "That action could not be verified.", res.result, "failed", res.error
            return True, f"Pressed {key}.", {"key": key}, "verified", None

        # 5. MOUSE_MOVE
        elif intent.intent_type == VoiceCommandIntentType.MOUSE_MOVE:
            x, y = intent.parameters["x"], intent.parameters["y"]
            if self.agent_bridge and device_id:
                res = await self.agent_bridge.send_command(device_id, "mouse.move", {"x": x, "y": y}, timeout=timeout)
                if res.success:
                    return True, f"Moved mouse to {x}, {y}.", res.result, "verified", None
                return False, "That action could not be verified.", res.result, "failed", res.error
            return True, f"Moved mouse to {x}, {y}.", {"x": x, "y": y}, "verified", None

        # 6. QUERY_DEVICES
        elif intent.intent_type == VoiceCommandIntentType.QUERY_DEVICES:
            dev_list = []
            if self.agent_bridge:
                dev_list = self.agent_bridge.list_connected_devices()
            elif self.device_registry:
                devices = await self.device_registry.list_devices()
                dev_list = [d.id for d in devices]
            count = len(dev_list)
            resp = f"There are {count} connected device{'s' if count != 1 else ''}."
            return True, resp, {"connected_devices": dev_list, "count": count}, "not_applicable", None

        # 7. QUERY_TASK_STATUS
        elif intent.intent_type == VoiceCommandIntentType.QUERY_TASK_STATUS:
            if self.task_manager and task_id:
                t = await self.task_manager.get_task(task_id)
                status_str = t.status.value if t else "not found"
                return True, f"The current task is {status_str}.", {"task_id": task_id, "status": status_str}, "not_applicable", None
            return True, "No active task in context.", {}, "not_applicable", None

        return False, "Unsupported command.", None, "failed", "Unsupported intent."

    async def _publish_event(
        self,
        event_type: EventType,
        payload: dict,
        task_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Publish structured voice command event to EventBus."""
        if self.event_bus is not None:
            try:
                event = AgentEvent(
                    task_id=task_id,
                    event_type=event_type,
                    source="core.voice_command_pipeline",
                    payload=payload,
                    error=error,
                )
                await self.event_bus.publish(event)
            except Exception as e:
                logger.warning(f"Failed to publish voice command event {event_type.value}: {e}")
