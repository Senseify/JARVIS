# JARVIS OS Architecture Documentation

## 1. System Overview

JARVIS OS is architected as an autonomous personal AI system structured around a centralized asynchronous Core coordinating with modular, generic device agents.

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Layer                           │
│     (Text / Voice / Desktop Orb & HUD / Notifications)      │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                       JARVIS Core                           │
│  - FastAPI / Uvicorn Server                                 │
│  - Settings & Lifecycle Management                          │
│  - Agent Loop State Machine (Observe -> Remember)           │
│  - Future: Memory, Task Manager, Planner, Device Registry   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                   Device Agent Layer                        │
│  - Windows Agent (Screen, Mouse, Keyboard, Window, Process) │
│  - Future iPad Companion (Notifications, Status Relay)      │
└─────────────────────────────────────────────────────────────┘
```

## 2. Core Agent Loop (FSM)

The execution flow of any task is governed by 8 formal states:
1. `idle`: Ready for task or user input.
2. `observe`: Adaptive environmental observation (active window, screen context, system metrics).
3. `understand`: Semantic synthesis of observed context.
4. `plan`: Action plan generation or adjustment.
5. `act`: Dispatch of authorized, discrete operations.
6. `verify`: Post-action state verification.
7. `recover`: Error diagnosis and fallback strategies on verification failure.
8. `remember`: Context storage and long-term memory persistence.

## 3. Technology Choices

- **Language Runtime**: Python 3.12 (Supported range: `>=3.11, <3.14`).
  - *Rationale*: Python 3.12 provides the most robust, mature pre-built wheel ecosystem across ARM64 (Apple Silicon) and x86_64 (Windows/Linux) for core dependencies including `pydantic-core`, `uvicorn`, and `fastapi`.
- **API Framework**: FastAPI + Uvicorn standard.
- **Settings & Validation**: Pydantic v2 + Pydantic-Settings.
- **Testing**: Pytest + Pytest-Asyncio + HTTPX.
