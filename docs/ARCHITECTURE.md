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
│  - FastAPI / Uvicorn Server & WebSocket Event Bus           │
│  - Settings & Lifecycle Management                          │
│  - Agent Loop State Machine (Observe -> Remember)           │
│  - Task Manager & State Transition Validation               │
│  - Async Agent Runtime & Per-Task Execution Context         │
│  - Tool / Skill Registry (Generic Abstraction)              │
│  - Device Registry & Agent Bridge (/ws/agent)               │
│  - SQLite Persistence (Tasks, Events, Devices)              │
└──────────────────────────────┬──────────────────────────────┘
                               │ WebSocket Bridge (/ws/agent)
┌──────────────────────────────▼──────────────────────────────┐
│                   Windows Agent Layer                       │
│  - Standalone Client Process                                │
│  - Handshake & Capability Discovery (system.info, etc.)     │
│  - Heartbeat & Uptime Monitoring                            │
│  - Safe Capability Execution Dispatch                       │
│  - Future: Screen Observation, Window, Mouse & Keyboard     │
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

## 3. Windows Agent Bridge & Protocol

The machine-side Windows Agent interacts with Core over an asynchronous WebSocket channel (`/ws/agent`) using strongly typed envelopes (`AgentMessage`) with strict correlation IDs:
- **Registration**: `register` → `register_ack` (includes device ID, platform, hostname, version, capabilities).
- **Heartbeat**: Periodic ping `heartbeat` → `heartbeat_ack` (tracks agent health, uptime, and offline detection).
- **Command Dispatch**: Core dispatches `command_request` → Agent validates capability → executes handler → replies with `command_result`.
- **Safe Initial Capabilities**:
  - `agent.ping`: Confirms bidirectional communication and latency.
  - `system.info`: Reports host platform, architecture, hostname, and Python runtime.
  - `agent.status`: Reports uptime, connection status, and registered capability set.

## 4. Technology Choices

- **Language Runtime**: Python 3.12 (Supported range: `>=3.11, <3.14`).
  - *Rationale*: Python 3.12 provides the most robust, mature pre-built wheel ecosystem across ARM64 (Apple Silicon) and x86_64 (Windows/Linux) for core dependencies including `pydantic-core`, `uvicorn`, and `fastapi`.
- **API Framework**: FastAPI + Uvicorn standard.
- **Settings & Validation**: Pydantic v2 + Pydantic-Settings.
- **Persistence**: Async-wrapped SQLite3 (thread-pool driven, WAL mode, zero external C-dependencies).
- **Communication**: REST API for management + WebSockets for client events (`/ws/events`) and agent coordination (`/ws/agent`).
- **Testing**: Pytest + Pytest-Asyncio + HTTPX + Starlette TestClient.
