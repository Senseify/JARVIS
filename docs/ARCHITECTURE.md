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

## 7. Observation Subsystem & Screen Awareness (Phase 5)

Located in `windows_agent/observation/`, this subsystem gives JARVIS controlled, request-driven visual awareness of the Windows desktop without continuous screen streaming.

### 7.1 Screen Capture Subsystem (`ScreenCapture`)
- **Technology**: Fast, lightweight Windows-compatible screen grab via `mss` (using DirectX/GDI backends).
- **Request-Driven Execution**: Screen capture is triggered strictly on demand (e.g. before/after actions, on verification checks, or on errors). Continuous background streaming is forbidden.
- **Capabilities**:
  - Full-screen capture across primary or specified monitor indices.
  - Active monitor detection.
  - Configurable sub-region bounding box (`top`, `left`, `width`, `height`).
  - Active foreground window metadata extraction (HWND, window title, PID).
  - Clean platform handling: On Windows, invokes User32 APIs via `ctypes`; on non-Windows environments, operates safely without pretending a Windows display exists.

### 7.2 ScreenState Model
Structured representation of the desktop state without dumping heavy raw image arrays across Core communication channels:
- `capture_id`: Unique UUID4 identifying the observation.
- `timestamp`: UTC ISO 8601 timestamp.
- `width` & `height`: Resolution of the captured frame.
- `monitor_index`: 1-indexed monitor index.
- `active_window`: Dictionary of active foreground window title, handle, and PID.
- `file_path`: Local filesystem path to stored screenshot artifact.
- `metadata`: Monitor counts, bounding coordinates, and host platform indicators.

### 7.3 Temporary Observation Store (`ObservationStore`)
Short-lived temporary cache for observation screenshots:
- **Unique Storage**: Files named `obs_<capture_id>.png` in a designated temporary folder.
- **Configurable Retention**: Default `max_age_seconds` (e.g. 300s) and `max_items` (e.g. 50 entries).
- **Pruning & Lifecycle**: Automated age-based expiration and count-based pruning (oldest first).
- **No Permanent Retention**: Screenshots are purged automatically; `clear()` empties the store completely.

### 7.4 Adaptive Observation Policy (`AdaptiveObservationPolicy`)
Controls when observation is authorized according to task execution lifecycle:
- `IDLE`: Strictly no continuous capture or polling.
- `BEFORE_ACTION`: Screen capture only when explicitly requested (`pre_observe=True`).
- `AFTER_ACTION`: Screen capture executed when action requires verification.
- `VERIFYING`: Screen capture authorized to validate resulting state.
- `ERROR`: Screen capture executed on unexpected failure for diagnostics.
- `RECOVERING`: Screen capture authorized prior to remediation retry.

### 7.5 Verification Engine (`VerificationEngine`)
Deterministic verification subsystem checking actual observed state against expected conditions:
- **Primitives**:
  - `active_window_title`: Verifies foreground window title matches expected substring or exact text.
  - `window_exists`: Verifies target window is present in enumerated window list.
  - `window_is_visible`: Verifies window exists AND is marked visible.
  - `window_disappeared`: Verifies closed or absent window.
  - `screen_dimensions`: Verifies screen resolution satisfies minimum thresholds.
- **Structured Verification Results (`VerificationResult`)**:
  - `verification_id`: UUID4 for auditability.
  - `check_type`: Name of verified primitive.
  - `expected_condition`: Description of condition.
  - `observed_state`: Actual recorded state.
  - `passed`: Boolean pass/fail outcome.
  - `failure_reason`: Explanatory failure reason when check does not pass.
- **Honest Verification**: Verifier never claims success without actually inspecting observed state. Failures preserve diagnostic metadata without pretending success.

### 7.6 Action → Observe → Verify Flow (`action.verify`)
Composes execution, observation, and verification into a unified capability:
```
1. (Optional) Observe Pre-Action ScreenState
2. Execute Action Capability (e.g. app.launch, window.focus, mouse.click)
3. Observe Resulting Post-Action ScreenState
4. Enumerate Window States if verifying window properties
5. Run Deterministic Verification Check
6. Return Combined Action Receipt + Verification Result
```

## 8. Privacy and Security Model

1. **No Hidden Continuous Streaming**: The agent does not record or stream desktop video. Observations are discrete and explicit.
2. **Controlled Retention**: Image files exist only in short-lived temporary storage with strict retention pruning.
3. **Payload Separation**: Large image binaries remain local to the storage layer; only metadata, resolution, window context, and file references are transmitted across Core channels.
4. **Parameter Validation**: Strict Pydantic schemas forbid unvalidated extra fields and enforce positive bounds on capture coordinates.

## 9. Technology Choices

- **Language Runtime**: Python 3.12 (Supported range: `>=3.11, <3.14`).
- **Core Framework**: FastAPI + Uvicorn standard.
- **Validation**: Pydantic v2 schemas for all payloads and envelopes.
- **Persistence**: Async SQLite3 (thread-pool driven, WAL mode, zero external C-dependencies).
- **Communication**: REST API for management + WebSockets for client events (`/ws/events`) and agent coordination (`/ws/agent`).
- **Desktop Automation**: Native Windows User32 via standard library `ctypes` and safe `subprocess` calls.
- **Screen Awareness**: `mss` screen grab library + PIL/PNG formatting.

## 10. Status & Deferred Milestones

- **Implemented (Phase 1–5)**: Core runtime, SQLite persistence, WebSocket bridge, Windows Agent process, mouse/keyboard/window/allowlisted app automation, action receipts, request-driven screen capture, temporary observation store, deterministic verification engine, adaptive observation policy, and Action → Observe → Verify workflow.
- **Strictly Deferred**: OCR, computer vision, UI element recognition from pixels, LLM vision, virtual cursor overlay, floating Orb/HUD, voice recognition, wake words, iPad companion, remote internet networking, autonomous recovery loops.
