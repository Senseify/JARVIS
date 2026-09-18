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

## 8. Vision Foundation & Screen Understanding (Phase 6A)

Located in `windows_agent/vision/`, this subsystem allows JARVIS to turn captured screen images and window states into structured visual information and UI understanding.

```
SCREEN CAPTURE (Phase 5)
        │
        ▼
   VISION CACHE (keyed by observation_id)
   ┌────┴────────────────────────┐
   ▼                             ▼
OCR ENGINE              UI ELEMENT DETECTOR
(Text Regions & BBoxes)  (Native Controls, Rects & Centers)
   └────┬────────────────────────┘
        ▼
UNIFIED SCREEN UNDERSTANDING (ScreenUnderstanding Model)
        │
        ▼
EXTENDED VERIFICATION ENGINE (Text & UI Element Primitives)
```

### 8.1 OCR Subsystem (`OCREngine`)
- **Request-Driven**: Operates over an existing observation captured by Phase 5 or requests a new capture. Strictly avoids continuous background OCR.
- **Structured Output**: Extracted text regions contain `text`, `bounding_box` (`left`, `top`, `width`, `height`), `confidence` score (0.0 to 1.0), and `observation_id`.
- **Platform-Aware Execution**:
  - On Windows 10/11: Invokes native WinRT `Windows.Media.Ocr` via PowerShell bridge without requiring external heavyweight OCR binaries.
  - On non-Windows development environments: Operates with clean platform handling, returning structured empty regions without pretending Windows OCR ran.
  - Pluggable custom provider support for unit and integration testing.

### 8.2 Native UI Element Detection (`UIDetector`)
- **Accessibility & Control Prioritization**: Leverages native Windows Win32 User32 APIs (`EnumChildWindows`, `GetClassNameW`, `GetWindowTextW`, `GetWindowRect`, `IsWindowVisible`, `IsWindowEnabled`, `GetFocus`) rather than attempting imprecise pixel inference.
- **Detected Element Types**: `button`, `text_field`, `checkbox`, `radio_button`, `menu`, `window`, `link`, `static_text`, `combo_box`, `list_box`, and general controls.
- **Structured Model (`UIElement`)**:
  - `element_id`: Native HWND or identifier reference.
  - `element_type`: Classification string.
  - `name`: Text, title, or label.
  - `bounding_box`: Screen-space rectangle (`left`, `top`, `width`, `height`).
  - `center_point`: Computed center coordinates (`left + width // 2`, `top + height // 2`).
  - `is_enabled`, `is_visible`, `is_focused`: Real control states.
  - `interaction_capabilities`: Supported operations (`["click"]`, `["type", "clear", "focus"]`, etc.).
- **Honest Detection**: Does not invent elements when the underlying OS cannot identify them. Clean empty return on non-Windows hosts.

### 8.3 Coordinate Mapping
- Where a detected UI element has a valid bounding rectangle, its center coordinates (`x`, `y`) are automatically calculated and exposed in `center_point`.
- Prepares the foundation for future agency to bridge `visual element → coordinates → mouse action`.
- Strictly does not click detected elements automatically in this milestone.

### 8.4 Vision Caching (`VisionCache`)
- Memory-bounded, TTL-backed cache keyed by `observation_id`.
- Reuses OCR extractions and UI element detections when querying the same observation repeatedly.
- Flushed on lifecycle eviction; does not create a permanent database of images or results.

### 8.5 Unified Screen Understanding (`ScreenUnderstanding`)
- Standard composite schema consumable by future JARVIS reasoning:
  - `observation_id`: ID of the visual observation.
  - `timestamp`: UTC ISO 8601 timestamp.
  - `screen_state`: Underlying Phase 5 screen state.
  - `active_window`: Active foreground window context.
  - `text_regions`: List of extracted `TextRegion` instances.
  - `ui_elements`: List of detected `UIElement` instances with center coordinates.

### 8.6 Extended Verification Engine
Extends deterministic verification with vision-aware primitives:
- `verify_text_present(expected_text, text_regions, case_sensitive=False)`
- `verify_text_absent(expected_text, text_regions, case_sensitive=False)`
- `verify_ui_element(ui_elements, name=None, element_type=None, is_enabled=None, is_visible=None)`
- Supported conditions in `verify_condition` and `action.verify`:
  - `text_present`, `ocr_text_present`
  - `text_absent`, `ocr_text_absent`
  - `ui_element_exists`, `ui_element`, `ui_element_visible`, `ui_element_enabled`
- Returns standard `VerificationResult` architecture; never claims verification success without inspecting detected evidence.

### 8.7 Vision Capabilities
- `screen.ocr`: Validates `ScreenOCRParams`, extracts OCR text regions from specified or newly captured observation.
- `screen.ui_elements`: Validates `ScreenUIElementsParams`, discovers native UI controls and coordinates.
- `screen.understand`: Validates `ScreenUnderstandParams`, returns complete `ScreenUnderstanding`.

## 9. Persistent Memory Engine (Phase 6B)

Located in `core/memory/` and `core/models/memory.py`, this subsystem provides a platform-independent, deterministic, persistent memory store that survives JARVIS process restarts.

```
REST API (/memories) / Runtime (REMEMBER)
                 │
                 ▼
          MemoryService
  ┌──────────────┴──────────────┐
  ▼                             ▼
Deduplication            Deterministic Scoring
(Normalize & Merge)      (Keywords, Tags, Type, Recency, Importance)
  └──────────────┬──────────────┘
                 ▼
            MemoryStore
                 │
                 ▼
       Async SQLite3 (memories)
```

### 9.1 Memory Model (`MemoryEntry`)
- `id`: UUID4 primary key.
- `memory_type`: Typed category:
  - `fact`: Factual statements or environment knowledge.
  - `preference`: User preferences (e.g. themes, modes, habits).
  - `instruction`: User-provided operating guidelines.
  - `task_context`: Context, inputs, and environment at task execution.
  - `observation`: Specific visual or environmental insights.
  - `outcome`: Results of completed or failed task executions.
  - `system`: System runtime and configuration notes.
- `content`: Primary text payload (min length 1, validated with Pydantic).
- `metadata`: Arbitrary JSON dictionary for structured context.
- `source`: Originator identifier (e.g. `user`, `agent_runtime`, `system`).
- `task_id`: Optional association to a specific task.
- `created_at` & `updated_at`: ISO 8601 UTC timestamps.
- `importance`: Float between 0.0 and 1.0.
- `tags`: List of categorical strings for tagging and filtering.
- `expires_at`: Optional expiration ISO timestamp for ephemeral retention.

### 9.2 Persistent SQLite Storage (`MemoryStore`)
- Operates on SQLite `memories` table with indexed `memory_type` and `task_id`.
- Complete CRUD operations: `store`, `get`, `list`, `update`, `delete`, `count`, `clear_by_task`, `clear_all`, and `prune_expired`.
- Fully persistent across application restarts without external services (no Redis, Postgres, or vector DBs).

### 9.3 Deduplication Engine
- Avoids memory clutter by detecting identical or equivalent entries using normalized text matching (`LOWER(TRIM(content))`) and category.
- When duplicate content is submitted:
  - Updates the `updated_at` timestamp.
  - Bumps importance to `max(existing.importance, new.importance)`.
  - Merges new tags and metadata into the existing entry.
  - Returns `is_new=False` without inserting redundant database rows.
- Can be explicitly bypassed when duplicate entries are intentionally desired (`allow_duplicate=True`).

### 9.4 Deterministic Relevance Ranking
Calculates relevance without relying on non-deterministic LLMs or heavy embeddings:
1. **Keyword Overlap (0.40 max)**: Query token frequency matching in content + exact substring bonus.
2. **Tag Overlap (0.25 max)**: Ratio of target tags matched against memory entry tags.
3. **Category Alignment (0.15 max)**: Memory type matching bonus.
4. **Importance (0.10 max)**: Scaled contribution of entry's importance score.
5. **Recency Factor (0.10 max)**: Smooth time decay based on elapsed hours since `updated_at`.
- Deterministic sort order: `relevance_score DESC`, `updated_at DESC`, `id ASC`.

### 9.5 Runtime Integration (`REMEMBER` Stage)
- Integrated into `AgentRuntime._remember_stage`:
  - Automatically records `task_context` memory referencing `task.id`.
  - Automatically records `outcome` memory summarizing action and verification counts upon successful completion.
  - Automatically records `outcome` failure details if recovery attempts are exhausted.
  - Selective and concise: avoids memory spam while ensuring critical continuity.

### 9.6 Core REST Endpoints
- `POST /memories`: Create memory with deduplication.
- `GET /memories`: Search memories by `q`, `type`, `tag`, `task_id`, `min_importance`, and `limit`.
- `GET /memories/{id}`: Retrieve single memory.
- `PATCH /memories/{id}`: Update memory content, importance, tags, or metadata.
- `DELETE /memories/{id}`: Delete individual memory.
- `DELETE /memories/task/{task_id}`: Clear memories tied to a specific task.

## 10. Skills Engine

Located in `core/skills/`, the Skills Engine provides a deterministic, reusable workflow abstraction composing existing capabilities and tools:

```
Agent → Skill → Tools/Capabilities → Observe → Verify → Result → Remember
```

A Skill is NOT a new tool or an LLM agent prompt. It is a strictly validated, multi-step deterministic workflow execution engine.

### 10.1 Structured Models
- **`SkillStep`**: Represents an individual atomic step targeting a capability or tool. Includes `parameters_template` supporting typed variable interpolation (e.g. `{app_name}`), optional `expected_condition`, `expected_value`, per-step `timeout`, and `continue_on_failure` policy.
- **`SkillDefinition`**: Complete specification including unique `id`, `name`, `description`, `version`, `required_capabilities`, ordered `steps`, overall `timeout`, `verification_requirements`, `input_schema`, and `output_schema`.
- **`SkillStepResult`**: Execution receipt recording `step_id`, `capability`, `status` (`success`, `failed`, `skipped`), `output`, `error`, `duration_ms`, `verified` flag, and `verification_details`.
- **`SkillExecution`**: Runtime execution tracking record with UUID `execution_id`, timestamps, step result trail, and persisted memory ID.
- **`SkillResult`**: Structured response returned to API callers and runtime callers with final status, step receipts, output payload, and duration.

### 10.2 Skill Registry (`SkillRegistry`)
- Maintains registered skill definitions in-memory.
- Enforces unique IDs and strictly rejects duplicate registrations.
- Provides capability inspection: `check_capabilities(skill_id, available_capabilities)` returns whether all prerequisites are met and reports missing capabilities.

### 10.3 Skill Executor (`SkillExecutor`)
- Coordinates the complete workflow lifecycle:
  1. Validates inputs against `input_schema`, checking required parameters and assigning defaults.
  2. Resolves target machine agent and verifies required capabilities are available.
  3. Recursively interpolates parameter templates preserving primitives (int, bool, float, strings, dicts).
  4. Dispatches steps sequentially to the target device via `AgentBridge` or local `ToolRegistry`.
  5. Evaluates verification receipts from `action.verify` or visual checks; halts immediately on failure unless `continue_on_failure` is explicitly enabled.
  6. Enforces per-step and global execution timeouts.
  7. Formulates structured `SkillResult`.

### 10.4 Skill ↔ Memory Integration
- Skills interface with `MemoryService` to persist high-level execution outcomes:
  - Stores a single `MemoryType.OUTCOME` entry summarizing success or failure reason.
  - Links associated `task_id` when executed in context of a task.
  - Strictly avoids spam: individual intermediate steps are **never** stored as permanent memories.

### 10.5 Built-In Skills
- **`launch_and_verify`**: Launches an allowlisted desktop application (`app.launch`) and verifies window presence (`window_open`).
- **`type_and_verify`**: Types text into the active foreground window (`keyboard.type`) with optional OCR verification (`text_present`).
- **`click_and_verify`**: Clicks at specified screen coordinates (`mouse.click`) and verifies desktop/UI condition.

### 10.6 Core REST Endpoints
- `GET /skills`: List all registered skill definitions.
- `GET /skills/{skill_id}`: Retrieve a specific skill definition.
- `POST /skills/{skill_id}/execute`: Execute a skill with input parameters, returning structured `SkillResult`.

## 11. Privacy and Security Model

1. **No Hidden Continuous Streaming**: The agent does not record or stream desktop video.
2. **Local-Only Persistence**: Memories and observations reside strictly on the local host SQLite database. No cloud memory, external vector APIs, or third-party telemetry.
3. **Task Deletion & Retention**: Users can delete memories individually or flush all memories associated with specific tasks.
4. **Expiration Support**: Ephemeral memories support `expires_at` and are automatically filtered out and pruned.
5. **Payload Separation**: Large image binaries remain local to the observation layer; memories store text, metadata, and identifiers.
6. **Strict Safety Boundaries**: Skills do not execute arbitrary shell commands, unvetted binaries, or unrestricted code. Applications remain strictly bounded to the explicit allowlist.

## 12. Technology Choices

- **Language Runtime**: Python 3.12 (Supported range: `>=3.11, <3.14`).
- **Core Framework**: FastAPI + Uvicorn standard.
- **Validation**: Pydantic v2 schemas for all payloads and envelopes.
- **Persistence**: Async SQLite3 (thread-pool driven, WAL mode, zero external C-dependencies).
- **Communication**: REST API for management + WebSockets for client events (`/ws/events`) and agent coordination (`/ws/agent`).
- **Desktop Automation**: Native Windows User32 via standard library `ctypes` and safe `subprocess` calls.
- **Screen Awareness**: `mss` screen grab library + PIL/PNG formatting.
- **Vision Foundation**: Native WinRT Windows Media OCR via PowerShell bridge + User32 child window control inspection.
- **Memory Engine**: Native SQLite3 schema with deterministic relevance scoring and deduplication.
- **Skills Engine**: Deterministic multi-step workflow executor with capability checking, Action → Observe → Verify orchestration, and memory outcome persistence.

## 13. Status & Deferred Milestones

- **Implemented (Phases 1–6C)**: Core runtime, SQLite persistence, WebSocket bridge, Windows Agent process, mouse/keyboard/window/allowlisted app automation, action receipts, request-driven screen capture, temporary observation store, deterministic verification engine, adaptive observation policy, Action → Observe → Verify workflow, OCR extraction, native UI element detection, coordinate mapping, vision caching, unified ScreenUnderstanding, persistent MemoryEntry model, SQLite MemoryStore, MemoryService with deduplication and deterministic scoring, Core REST memory endpoints, AgentRuntime REMEMBER stage integration, SkillDefinition and workflow step models, SkillRegistry with capability checking, SkillExecutor with deterministic step dispatch, error halting, and MemoryService outcome persistence, built-in skills (`launch_and_verify`, `type_and_verify`, `click_and_verify`), and Core REST skills endpoints (`/skills`).
- **Strictly Deferred**: LLM reasoning/planning, autonomous agent loops beyond existing runtime, voice recognition, wake words, floating Orb/HUD, virtual cursor overlay, iPad companion, multi-device routing, Marvel/Unity integration.
