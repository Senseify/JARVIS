"""Main entrypoint and FastAPI application factory for JARVIS OS Core."""

from fastapi import FastAPI
from core import __version__
from core.config import settings
from core.constants import AgentLoopState


def create_app() -> FastAPI:
    """Create and configure the FastAPI application for JARVIS OS Core."""
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Autonomous Personal AI Agent Core API",
    )

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
        }

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
