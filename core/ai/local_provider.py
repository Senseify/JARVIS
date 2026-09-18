"""Local AI Model Providers for JARVIS OS.

Supports:
1. LocalModelProvider: Connects to local OpenAI-compatible inference backends
   (Ollama, llama.cpp, LocalAI, vLLM) without requiring any cloud API key.
2. DeterministicLocalProvider: Fully offline, zero-network embedded reasoner
   producing deterministic tool calls and conversational responses for testing
   and resource-constrained environments.
"""

import json
import logging
import re
import time
from typing import Any
import httpx

from core.ai.provider import BaseModelProvider
from core.models.ai import (
    ChatMessage,
    ModelCapabilities,
    ModelRequest,
    ModelResponse,
    ModelRole,
    ModelRuntimeInfo,
    ToolCallDefinition,
)

logger = logging.getLogger(__name__)


class LocalModelProvider(BaseModelProvider):
    """Provider connecting to local inference servers (Ollama, llama.cpp, vLLM)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model_name: str = "llama3.2:latest",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self._capabilities = ModelCapabilities(
            model_id=self.model_name,
            supports_tools=True,
            supports_vision=False,
            supports_streaming=True,
            context_window=8192,
            local_only=True,
            description=f"Local inference via {self.base_url}",
        )

    def get_capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def get_runtime_info(self) -> ModelRuntimeInfo:
        return ModelRuntimeInfo(
            model_id=self.model_name,
            provider_type="local_http",
            status="ready",
            device="local_inference_server",
            loaded=True,
            endpoint=self.base_url,
        )

    async def check_health(self) -> bool:
        """Check if local inference backend is reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/models")
                return res.status_code == 200
        except Exception as exc:
            logger.debug("LocalModelProvider health check failed: %s", exc)
            return False

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Forward completion request to local endpoint."""
        start_time = time.perf_counter()
        messages = [{"role": msg.role.value, "content": msg.content} for msg in request.messages]

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            payload["tools"] = request.tools

        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                res = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                res.raise_for_status()
                data = res.json()

            choice = data["choices"][0]
            message_data = choice["message"]
            content = message_data.get("content") or ""
            tool_calls: list[ToolCallDefinition] = []

            if "tool_calls" in message_data and message_data["tool_calls"]:
                for raw_call in message_data["tool_calls"]:
                    fn = raw_call.get("function", {})
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(ToolCallDefinition(tool=name, arguments=args))

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ModelResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=choice.get("finish_reason", "stop"),
                usage=data.get("usage", {}),
                model_name=self.model_name,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            logger.error("Local inference error: %s", exc)
            return ModelResponse(
                content=f"Local model unavailable or error occurred: {exc}",
                tool_calls=[],
                finish_reason="error",
                model_name=self.model_name,
                duration_ms=(time.perf_counter() - start_time) * 1000.0,
            )


class DeterministicLocalProvider(BaseModelProvider):
    """Zero-dependency deterministic local reasoner.

    Provides reliable reasoning, tool extraction, and natural language generation
    without requiring external model server processes or heavy model weights.
    """

    def __init__(self, model_id: str = "jarvis-deterministic-v1") -> None:
        self.model_id = model_id
        self._capabilities = ModelCapabilities(
            model_id=self.model_id,
            supports_tools=True,
            supports_vision=False,
            supports_streaming=False,
            context_window=16384,
            local_only=True,
            description="Embedded deterministic local reasoner",
        )

    def get_capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def get_runtime_info(self) -> ModelRuntimeInfo:
        return ModelRuntimeInfo(
            model_id=self.model_id,
            provider_type="deterministic_embedded",
            status="ready",
            device="cpu",
            loaded=True,
            memory_usage_mb=12.5,
            endpoint="embedded://core",
        )

    async def check_health(self) -> bool:
        return True

    async def generate(self, request: ModelRequest) -> ModelResponse:
        start_time = time.perf_counter()
        last_msg = request.messages[-1].content if request.messages else ""
        query = last_msg.strip().lower()

        tool_calls: list[ToolCallDefinition] = []
        response_content = ""

        # Analyze request for desktop actions
        # 1. Multi-step: "open notepad and type hello world"
        multi_match = re.match(
            r"(?:open|launch)\s+([a-zA-Z0-9_\-]+)\s+and\s+(?:type|write)\s+[\"']?(.*?)[\"']?$",
            query,
        )
        if multi_match:
            app_name = multi_match.group(1).strip()
            text_to_type = multi_match.group(2).strip()
            tool_calls.append(ToolCallDefinition(tool="app.launch", arguments={"app": app_name}))
            tool_calls.append(ToolCallDefinition(tool="keyboard.type", arguments={"text": text_to_type}))
            response_content = f"Launching {app_name} and typing '{text_to_type}'."

        # 2. Simple launch: "open notepad", "launch calculator"
        elif re.match(r"^(?:open|launch)\s+([a-zA-Z0-9_\-]+)$", query):
            app = re.match(r"^(?:open|launch)\s+([a-zA-Z0-9_\-]+)$", query).group(1).strip()
            tool_calls.append(ToolCallDefinition(tool="app.launch", arguments={"app": app}))
            response_content = f"Launching {app}."

        # 3. Type text: "type hello world"
        elif query.startswith("type ") or query.startswith("write "):
            text = last_msg[len("type "):].strip().strip('"\'')
            tool_calls.append(ToolCallDefinition(tool="keyboard.type", arguments={"text": text}))
            response_content = f"Typing: {text}"

        # 4. Press key: "press enter", "hotkey ctrl+c"
        elif query.startswith("press ") or query.startswith("hotkey "):
            key = query.split(" ", 1)[1].strip()
            tool = "keyboard.hotkey" if "+" in key else "keyboard.press"
            tool_calls.append(ToolCallDefinition(tool=tool, arguments={"key": key}))
            response_content = f"Pressing {key}."

        # 5. Mouse actions: "click", "double click", "move mouse to 100 200"
        elif "click" in query or "move mouse" in query:
            move_match = re.search(r"move\s+(?:mouse\s+)?to\s+(\d+)\s+(\d+)", query)
            if move_match:
                x, y = int(move_match.group(1)), int(move_match.group(2))
                tool_calls.append(ToolCallDefinition(tool="mouse.move", arguments={"x": x, "y": y}))
                response_content = f"Moving mouse to ({x}, {y})."
            elif "double" in query:
                tool_calls.append(ToolCallDefinition(tool="mouse.double_click", arguments={}))
                response_content = "Double clicking."
            else:
                tool_calls.append(ToolCallDefinition(tool="mouse.click", arguments={"button": "left"}))
                response_content = "Clicking."

        # 6. Conversational / Informational queries (no tool calls)
        else:
            if any(k in query for k in ["who are you", "what are you", "identify yourself"]):
                response_content = (
                    "I am JARVIS, an autonomous personal AI agent operating locally on your system. "
                    "I can plan and execute desktop tasks, observe and verify screen actions, and converse with you."
                )
            elif any(k in query for k in ["hello", "hi", "hey"]):
                response_content = "Greetings. I am online and ready to assist you. What shall we accomplish?"
            elif "status" in query:
                response_content = "All core subsystems are operational. Local reasoning and verified execution are active."
            else:
                response_content = (
                    f"I have processed your request: '{last_msg}'. "
                    "I can assist with desktop automation, information retrieval, or multi-step tasks."
                )

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return ModelResponse(
            content=response_content,
            tool_calls=tool_calls,
            finish_reason="stop",
            usage={"prompt_tokens": len(last_msg.split()), "completion_tokens": len(response_content.split())},
            model_name=self.model_id,
            duration_ms=duration_ms,
        )
