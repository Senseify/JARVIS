"""Main entrypoint and FastAPI application factory for JARVIS OS Core."""

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from core import __version__
from core.config import settings
from core.constants import AgentLoopState
from core.devices.agent_bridge import AgentBridge
from core.devices.registry import DeviceRegistry
from core.events.bus import EventBus
from core.memory.service import MemoryService
from core.memory.store import MemoryStore
from core.models.devices import Device, DeviceCreateRequest
from core.models.events import AgentEvent
from core.models.memory import (
    MemoryCreateRequest,
    MemoryEntry,
    MemorySearchResult,
    MemoryType,
    MemoryUpdateRequest,
)
from core.models.protocol import CommandDispatchRequest, CommandResultPayload
from core.models.skills import (
    SkillDefinition,
    SkillExecuteRequest,
    SkillResult,
)
from core.models.tasks import Task, TaskCreateRequest, TaskStatusResponse
from core.models.voice import (
    SpeechRecognitionResult,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    VoiceInput,
    VoiceState,
)
from core.models.voice_command import (
    VoiceCommandRequest,
    VoiceCommandResult,
)
from core.persistence.database import Database
from core.runtime.agent_runtime import AgentRuntime
from core.skills.builtin import get_builtin_skills
from core.skills.executor import SkillExecutor
from core.skills.registry import SkillRegistry
from core.tasks.manager import TaskManager
from core.tools.demo import DemoVerificationTool
from core.tools.registry import ToolRegistry
from core.voice.command_service import VoiceCommandService
from core.voice.service import VoiceService
from core.voice.stt import DeterministicSTTProvider
from core.voice.tts import DeterministicTTSProvider
from core.ai.engine import ReasoningEngine
from core.ai.manager import ModelManager
from core.knowledge.service import KnowledgeService
from core.models.ai import ChatRequest, ChatResponse, ModelRuntimeInfo
from core.models.planning import Plan
from core.planning.planner import AutonomousPlanner
from core.planning.recovery import RecoveryEngine
from core.security.policy import SecurityPolicyEngine
import os
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


class RuntimeContainer:
    """Dependency container holding core runtime subsystems."""

    def __init__(self, db_path: str = settings.database_path):
        self.db_path = db_path
        self.database = Database(db_path=self.db_path)
        self.event_bus = EventBus(database=self.database)
        self.tool_registry = ToolRegistry()
        self.device_registry = DeviceRegistry(database=self.database)
        self.agent_bridge = AgentBridge(device_registry=self.device_registry)
        self.task_manager = TaskManager(database=self.database, event_bus=self.event_bus)
        self.memory_store = MemoryStore(database=self.database)
        self.memory_service = MemoryService(store=self.memory_store)
        self.agent_runtime = AgentRuntime(
            task_manager=self.task_manager,
            tool_registry=self.tool_registry,
            event_bus=self.event_bus,
            memory_service=self.memory_service,
        )
        self.skill_registry = SkillRegistry()
        for builtin in get_builtin_skills():
            self.skill_registry.register_skill(builtin)
        self.skill_executor = SkillExecutor(
            registry=self.skill_registry,
            agent_bridge=self.agent_bridge,
            tool_registry=self.tool_registry,
            memory_service=self.memory_service,
        )
        self.voice_service = VoiceService(
            stt_provider=DeterministicSTTProvider(),
            tts_provider=DeterministicTTSProvider(),
            event_bus=self.event_bus,
        )
        self.model_manager = ModelManager()
        self.security_policy = SecurityPolicyEngine()
        self.recovery_engine = RecoveryEngine(event_bus=self.event_bus)
        self.planner = AutonomousPlanner(
            security_policy=self.security_policy,
            tool_registry=self.tool_registry,
        )
        self.knowledge_service = KnowledgeService()
        self.reasoning_engine = ReasoningEngine(
            model_manager=self.model_manager,
            planner=self.planner,
            recovery_engine=self.recovery_engine,
            security_policy=self.security_policy,
            memory_service=self.memory_service,
            knowledge_service=self.knowledge_service,
            skill_executor=self.skill_executor,
            agent_bridge=self.agent_bridge,
            task_manager=self.task_manager,
            event_bus=self.event_bus,
        )
        self.voice_command_service = VoiceCommandService(
            voice_service=self.voice_service,
            skill_executor=self.skill_executor,
            task_manager=self.task_manager,
            agent_bridge=self.agent_bridge,
            device_registry=self.device_registry,
            memory_service=self.memory_service,
            event_bus=self.event_bus,
            reasoning_engine=self.reasoning_engine,
        )


def create_app(container: Optional[RuntimeContainer] = None) -> FastAPI:
    """Create and configure the FastAPI application for JARVIS OS Core."""
    rt = container or RuntimeContainer()

    # Active WebSocket clients for UI/Runtime events
    active_websockets: set[WebSocket] = set()

    async def broadcast_to_websockets(event: AgentEvent) -> None:
        """Broadcast an agent event to all connected WebSocket clients."""
        dead_sockets = set()
        event_json = event.model_dump_json()
        for ws in list(active_websockets):
            try:
                await ws.send_text(event_json)
            except Exception:
                dead_sockets.add(ws)

        for dead_ws in dead_sockets:
            active_websockets.discard(dead_ws)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        await rt.database.connect()
        if settings.enable_demo_tool:
            rt.tool_registry.register_tool(DemoVerificationTool())
        rt.event_bus.subscribe(broadcast_to_websockets)
        yield
        # Shutdown
        rt.event_bus.unsubscribe(broadcast_to_websockets)
        await rt.database.close()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Autonomous Personal AI Agent Core API",
        lifespan=lifespan,
    )

    # Attach container to app state for access in route handlers
    app.state.runtime = rt

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------------------------------------------
    # System Info & Health
    # -------------------------------------------------------------
    @app.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
        }

    @app.get("/info")
    async def info():
        return {
            "app": settings.app_name,
            "version": __version__,
            "agent_loop_states": [state.value for state in AgentLoopState],
            "registered_tools": [t.name for t in rt.tool_registry.list_tools()],
            "connected_agents": rt.agent_bridge.list_connected_devices(),
        }

    # -------------------------------------------------------------
    # Task Endpoints
    # -------------------------------------------------------------
    @app.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
    async def create_task(req: TaskCreateRequest):
        task = await rt.task_manager.create_task(req.input, metadata=req.metadata)
        if req.execute_immediately:
            asyncio.create_task(rt.agent_runtime.execute_task(task.id))
        return task

    @app.get("/tasks", response_model=List[Task])
    async def list_tasks(limit: int = 50, offset: int = 0):
        return await rt.task_manager.list_tasks(limit=limit, offset=offset)

    @app.get("/tasks/{task_id}", response_model=Task)
    async def get_task(task_id: str):
        task = await rt.task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return task

    @app.get("/tasks/{task_id}/status", response_model=TaskStatusResponse)
    async def get_task_status(task_id: str):
        task = await rt.task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return TaskStatusResponse(
            id=task.id,
            state=task.state,
            status=task.status,
            created_at=task.created_at,
            updated_at=task.updated_at,
            error=task.error,
        )

    @app.get("/tasks/{task_id}/events", response_model=List[AgentEvent])
    async def get_task_events(task_id: str):
        return await rt.database.get_events_for_task(task_id)

    @app.post("/tasks/{task_id}/execute", response_model=Task)
    async def execute_task(task_id: str):
        task = await rt.task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return await rt.agent_runtime.execute_task(task_id)

    # -------------------------------------------------------------
    # Device & Agent Endpoints
    # -------------------------------------------------------------
    @app.post("/devices", response_model=Device, status_code=status.HTTP_201_CREATED)
    async def register_device(req: DeviceCreateRequest):
        device = Device(
            name=req.name,
            device_type=req.device_type,
            capabilities=req.capabilities,
            metadata=req.metadata,
        )
        if req.id:
            device.id = req.id
        await rt.device_registry.register(device)
        return device

    @app.get("/devices", response_model=List[Device])
    async def list_devices():
        return await rt.device_registry.list_devices()

    @app.post("/devices/{device_id}/command", response_model=CommandResultPayload)
    async def dispatch_device_command(device_id: str, req: CommandDispatchRequest):
        if not rt.agent_bridge.is_connected(device_id):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Device '{device_id}' is not currently connected to Core.",
            )
        try:
            result = await rt.agent_bridge.send_command(
                device_id=device_id,
                capability=req.capability,
                parameters=req.parameters,
                timeout=req.timeout,
            )
            return result
        except KeyError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except TimeoutError as e:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # -------------------------------------------------------------
    # Tools Endpoint
    # -------------------------------------------------------------
    @app.get("/tools")
    async def list_tools():
        return rt.tool_registry.list_tools()

    # -------------------------------------------------------------
    # Memory Endpoints (Phase 6B)
    # -------------------------------------------------------------
    @app.post("/memories", status_code=status.HTTP_201_CREATED)
    async def create_memory(request: MemoryCreateRequest):
        entry, is_new = await rt.memory_service.store_memory(
            content=request.content,
            memory_type=request.memory_type,
            metadata=request.metadata,
            source=request.source,
            task_id=request.task_id,
            importance=request.importance,
            tags=request.tags,
            expires_at=request.expires_at,
            allow_duplicate=request.allow_duplicate,
        )
        return {"memory": entry, "is_new": is_new}

    @app.get("/memories")
    async def search_memories(
        q: Optional[str] = None,
        type: Optional[str] = None,
        tag: Optional[str] = None,
        task_id: Optional[str] = None,
        min_importance: float = 0.0,
        limit: int = 20,
    ):
        tags = [tag] if tag else None
        return await rt.memory_service.search_memory(
            query=q,
            memory_type=type,
            tags=tags,
            task_id=task_id,
            min_importance=min_importance,
            limit=limit,
        )

    @app.get("/memories/{memory_id}")
    async def get_memory(memory_id: str):
        entry = await rt.memory_service.get_memory(memory_id)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory '{memory_id}' not found.",
            )
        return entry

    @app.patch("/memories/{memory_id}")
    async def update_memory(memory_id: str, request: MemoryUpdateRequest):
        updated = await rt.memory_service.update_memory(memory_id, request)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory '{memory_id}' not found.",
            )
        return updated

    @app.delete("/memories/{memory_id}")
    async def delete_memory(memory_id: str):
        deleted = await rt.memory_service.delete_memory(memory_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory '{memory_id}' not found.",
            )
        return {"deleted": True, "id": memory_id}

    @app.delete("/memories/task/{task_id}")
    async def clear_task_memories(task_id: str):
        count = await rt.memory_service.clear_task_memory(task_id)
        return {"deleted_count": count, "task_id": task_id}

    # -------------------------------------------------------------
    # Skills Endpoints (Phase 6C)
    # -------------------------------------------------------------
    @app.get("/skills", response_model=List[SkillDefinition])
    async def list_skills():
        return rt.skill_registry.list_skills()

    @app.get("/skills/{skill_id}", response_model=SkillDefinition)
    async def get_skill(skill_id: str):
        skill = rt.skill_registry.get_skill(skill_id)
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_id}' not found.",
            )
        return skill

    @app.post("/skills/{skill_id}/execute", response_model=SkillResult)
    async def execute_skill(skill_id: str, request: SkillExecuteRequest):
        if not rt.skill_registry.has_skill(skill_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_id}' not found.",
            )
        try:
            return await rt.skill_executor.execute(skill_id, request)
        except KeyError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except TimeoutError as e:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # -------------------------------------------------------------
    # Voice Endpoints (Voice Foundation)
    # -------------------------------------------------------------
    @app.get("/voice/status", response_model=VoiceState)
    async def get_voice_status():
        return await rt.voice_service.get_status()

    @app.post("/voice/transcribe", response_model=SpeechRecognitionResult)
    async def transcribe_voice(voice_input: VoiceInput):
        try:
            return await rt.voice_service.transcribe(voice_input)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    @app.post("/voice/speak", response_model=SpeechSynthesisResult)
    async def speak_text(request: SpeechSynthesisRequest):
        try:
            return await rt.voice_service.speak(request)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # -------------------------------------------------------------
    # Voice Command Pipeline Endpoints (Phase 8)
    # -------------------------------------------------------------
    @app.post("/voice/command", response_model=VoiceCommandResult)
    async def execute_voice_command(request: VoiceCommandRequest):
        try:
            return await rt.voice_command_service.execute_voice_command(request)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    @app.post("/voice/command/text", response_model=VoiceCommandResult)
    async def execute_voice_command_text(text: str):
        try:
            req = VoiceCommandRequest(text_override=text)
            return await rt.voice_command_service.execute_voice_command(req)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # -------------------------------------------------------------
    # System Status & Diagnostics Endpoints (Phases 9-16)
    # -------------------------------------------------------------
    @app.get("/system/status")
    async def get_system_status():
        """Comprehensive system diagnostics for JARVIS Core."""
        active_model_info = rt.model_manager.get_active_info()
        connected_devices = rt.agent_bridge.list_connected_devices()
        skills = [s.name for s in rt.skill_registry.list_skills()]
        tools = [t.name for t in rt.tool_registry.list_tools()]
        memory_count = await rt.memory_store.count()

        return {
            "status": "operational",
            "version": __version__,
            "core": {
                "running": True,
                "agent_loop": AgentLoopState.IDLE,
            },
            "model_runtime": active_model_info.model_dump(),
            "voice": {
                "status": "operational",
                "stt": rt.voice_service.stt_provider.__class__.__name__,
                "tts": rt.voice_service.tts_provider.__class__.__name__,
            },
            "memory": {
                "status": "operational",
                "total_entries": memory_count,
            },
            "connected_agents": connected_devices,
            "available_skills": skills,
            "registered_tools": tools,
            "security": {
                "allowlisted_apps": rt.security_policy.config.allowlisted_apps,
                "blocked_tools_count": len(rt.security_policy.config.blocked_tools),
            },
        }

    @app.get("/system/security/policy")
    async def get_security_policy():
        """Retrieve active security policy rules and allowlists."""
        return {
            "allowlisted_apps": rt.security_policy.config.allowlisted_apps,
            "blocked_tools": rt.security_policy.config.blocked_tools,
            "max_typing_length": rt.security_policy.config.max_typing_length,
            "allow_remote_control": rt.security_policy.config.allow_remote_control,
        }

    # -------------------------------------------------------------
    # AI & Reasoning Endpoints (Phases 9-16)
    # -------------------------------------------------------------
    @app.post("/ai/chat", response_model=ChatResponse)
    async def ai_chat(request: ChatRequest):
        """Process conversational or desktop automation task request."""
        try:
            return await rt.reasoning_engine.process_chat(request)
        except Exception as e:
            logger.error("AI chat error: %s", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    @app.get("/ai/models", response_model=List[ModelRuntimeInfo])
    async def list_models():
        """List registered local model providers."""
        return rt.model_manager.list_providers()

    @app.post("/ai/models/select")
    async def select_model(name: str):
        """Switch active model provider."""
        try:
            rt.model_manager.set_active_provider(name)
            return {"active_provider": name, "info": rt.model_manager.get_active_info()}
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @app.post("/ai/plan", response_model=Plan)
    async def create_plan(goal: str, tools: list[dict]):
        """Explicitly construct a validated multi-step plan."""
        from core.models.ai import ToolCallDefinition
        try:
            tool_calls = [ToolCallDefinition(tool=t.get("tool", ""), arguments=t.get("arguments", {})) for t in tools]
            return rt.planner.create_plan_from_tool_calls(goal=goal, tool_calls=tool_calls)
        except PermissionError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @app.get("/ai/plans", response_model=List[Plan])
    async def list_plans():
        """List tracked execution plans."""
        return rt.planner.list_plans()

    # Mount static web app if directory exists
    web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
    if os.path.exists(web_dir):
        app.mount("/ui", StaticFiles(directory=web_dir, html=True), name="web_ui")

        @app.get("/", include_in_schema=False)
        async def root_redirect():
            return RedirectResponse(url="/ui/")

    # -------------------------------------------------------------
    # WebSockets
    # -------------------------------------------------------------
    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        """Streaming channel for client UIs (Orb/HUD) receiving runtime events."""
        await websocket.accept()
        active_websockets.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            active_websockets.discard(websocket)

    @app.websocket("/ws/agent")
    async def websocket_agent(websocket: WebSocket):
        """Dedicated bridge channel for machine agents (e.g. Windows Agent)."""
        await rt.agent_bridge.handle_agent_connection(websocket)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "core.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
