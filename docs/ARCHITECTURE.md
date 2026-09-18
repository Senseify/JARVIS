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
│  - Handshake & Capability Discovery                         │
│  - Heartbeat & Uptime Monitoring                            │
│  - Automation Subsystem (Mouse, Keyboard, Windows, Apps)    │
│  - Action Receipts & Parameter Validation                   │
└──────────────────────────────┬──────────────────────────────┘
                               │ Native User32 / Win32 APIs
┌──────────────────────────────▼──────────────────────────────┐
│                        Windows OS                           │
│  - Foreground Active Window & Enumeration                   │
│  - Hardware Input Ingestion (Cursor, Keystrokes)            │
│  - Allowlisted Desktop Applications                         │
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

## 3. Core → Agent → Windows OS Control Flow

```
JARVIS Core                  Windows Agent                       Windows OS
    │                              │                                 │
    ├─ POST /devices/{id}/command ─►                                 │
    │  (CommandRequestPayload)     ├─ Validate Request & Params      │
    │                              ├─ Lookup Allowlist / Bounds      │
    │                              ├─ Dispatch Controller Operation ─► Win32 Call (e.g. SetCursorPos)
    │                              │  (under ReceiptTracker)         │
    │                              │                                 ├─ Physical OS Action
    │                              ◄── Raw Result / Status ──────────┘
    │                              ├─ Generate ActionReceipt
    │  ◄─ CommandResultPayload ────┤  (start, end, duration, status)
    │     (with ActionReceipt)     │
    ▼                              ▼
```

## 4. Capability Architecture & Automation Boundary

The Windows Agent isolates all OS-specific automation within the `windows_agent/automation/` package:
- **Capability Mapping**:
  `Capability Name` → `Pydantic Parameter Validator` → `Automation Controller` → `Action Receipt`
- **Implemented Capabilities**:
  - `agent.ping`: Latency and ping check.
  - `system.info`: Platform, architecture, Python runtime, and host identity.
  - `agent.status`: Connection status, uptime, and supported capability list.
  - `mouse.move`: Cursor positioning (`x`, `y`, `duration`).
  - `mouse.click`: Single/multiple button clicks (`left`, `right`, `middle`).
  - `mouse.double_click`: Quick double-click execution.
  - `keyboard.type`: Keystroke typing with optional inter-key delay.
  - `keyboard.press`: Single key down/up event (`enter`, `tab`, `esc`, etc.).
  - `keyboard.hotkey`: Simultaneous modifier combinations (`['ctrl', 'c']`, etc.).
  - `window.list`: Top-level window enumeration with title, HWND, and PID.
  - `window.focus`: Brings window to foreground by HWND or title substring.
  - `app.launch`: Launches allowlisted desktop applications.

## 5. Application Allowlist & Security Model

To prevent arbitrary execution:
- Only applications configured in the explicit allowlist are permitted (`notepad`, `calc`/`calculator`, `mspaint`/`paint`, `explorer`).
- Rejects path traversal, slashes, or shell metacharacters (`;`, `&`, `|`, `` ` ``, `$`, `<`, `>`).
- Executables are invoked strictly via array arguments with `shell=False`.
- Unallowlisted applications raise `PermissionError` immediately.

## 6. Action Receipt Model

Every computer control command executed by the agent produces an `ActionReceipt`:
- `capability`: Name of capability invoked.
- `request_id`: Preserved correlation identifier.
- `start_time` & `end_time`: ISO 8601 UTC timestamps.
- `duration_ms`: High-precision monotonic execution duration in milliseconds.
- `success`: Boolean indicating verified execution success.
- `result`: Structured data returned by the automation controller.
- `error`: Error description if execution failed.

## 7. Technology Choices

- **Language Runtime**: Python 3.12 (Supported range: `>=3.11, <3.14`).
- **Core Framework**: FastAPI + Uvicorn standard.
- **Validation**: Pydantic v2 schemas for all payloads and envelopes.
- **Persistence**: Async SQLite3 (thread-pool driven, WAL mode, zero external C-dependencies).
- **Communication**: REST API for management + WebSockets for client events (`/ws/events`) and agent coordination (`/ws/agent`).
- **Desktop Automation**: Native Windows User32 via standard library `ctypes` and safe `subprocess` calls without heavy third-party automation dependencies.

## 8. Status & Deferred Milestones

- **Implemented**: Core runtime, SQLite persistence, WebSocket bridge, Windows Agent process, mouse/keyboard/window/allowlisted app automation, action receipts, typed validation.
- **Strictly Deferred**: Screen capture, OCR, computer vision, continuous screen streaming, virtual cursor overlay, floating Orb/HUD, voice recognition, wake words, iPad companion, remote internet networking, LLM provider integrations.
