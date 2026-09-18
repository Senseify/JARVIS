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
from core.devices.registry import DeviceRegistry
from core.events.bus import EventBus
from core.models.devices import Device, DeviceCreateRequest
from core.models.events import AgentEvent
from core.models.tasks import Task, TaskCreateRequest, TaskStatusResponse
from core.persistence.database import Database
from core.runtime.agent_runtime import AgentRuntime
from core.tasks.manager import TaskManager
from core.tools.demo import DemoVerificationTool
from core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class RuntimeContainer:
    """Dependency container holding core runtime subsystems."""

    def __init__(self, db_path: str = settings.database_path):
        self.db_path = db_path
        self.database = Database(db_path=self.db_path)
        self.event_bus = EventBus(database=self.database)
        self.tool_registry = ToolRegistry()
        self.device_registry = DeviceRegistry(database=self.database)
        self.task_manager = TaskManager(database=self.database, event_bus=self.event_bus)
        self.agent_runtime = AgentRuntime(
            task_manager=self.task_manager,
            tool_registry=self.tool_registry,
            event_bus=self.event_bus,
        )


def create_app(container: Optional[RuntimeContainer] = None) -> FastAPI:
    """Create and configure the FastAPI application for JARVIS OS Core."""
    rt = container or RuntimeContainer()

    # Active WebSocket clients
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
        }

    # -------------------------------------------------------------
    # Task Endpoints
    # -------------------------------------------------------------
    @app.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
    async def create_task(req: TaskCreateRequest):
        task = await rt.task_manager.create_task(req.input, metadata=req.metadata)
        if req.execute_immediately:
            # Execute asynchronously in the background so API stays responsive
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
    # Device Endpoints
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

    # -------------------------------------------------------------
    # Tools Endpoint
    # -------------------------------------------------------------
    @app.get("/tools")
    async def list_tools():
        return rt.tool_registry.list_tools()

    # -------------------------------------------------------------
    # WebSocket Event Stream
    # -------------------------------------------------------------
    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        await websocket.accept()
        active_websockets.add(websocket)
        try:
            while True:
                # Keep alive and receive any client messages or pings
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            active_websockets.discard(websocket)

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
