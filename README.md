# JARVIS OS

A real personal AI agent system inspired by JARVIS, designed for multi-step reasoning, adaptive computer awareness, and multi-device task execution.

---

## 1. Project Overview & Vision

JARVIS OS is not a generic text chatbot. It is an autonomous task-executing personal AI agent designed to:
- Understand natural language text and voice instructions.
- Reason about complex, multi-step tasks and produce actionable plans.
- Observe authorized computer screens through adaptive inspection.
- Understand visible UI and application state.
- Control authorized operating-system functions, applications, filesystem, and terminal operations.
- Verify outcomes after actions, recover gracefully from failures, and remember context across sessions.
- Coordinate seamlessly across authorized devices (desktop host, secondary companions) with strict permission controls.

---

## 2. Critical Project Boundaries

### Separation from Marvel: Ascension & Other Applications
**JARVIS OS and Marvel: Ascension are completely separate projects.**

- `Marvel: Ascension` is **NOT**:
  - a JARVIS module
  - a JARVIS dependency
  - a JARVIS skill
  - a JARVIS subsystem
  - a required application
  - part of the JARVIS architecture or memory schema

JARVIS OS must operate cleanly and reliably on any clean system without `Marvel: Ascension`, `Unity`, `VS Code`, or any specific proprietary software installed.

In the future, JARVIS may interact with such applications via **generic interfaces** (such as Application Control, Process Management, Window Control, and Filesystem Inspection), treating them identically to any standard application (like a browser or text editor).

---

## 3. Core Agent Loop

JARVIS OS is governed by a closed-loop execution model:

```
OBSERVE ───► UNDERSTAND ───► PLAN ───► ACT ───► VERIFY ───► REMEMBER
                                ▲                  │
                                └─── RECOVER ◄─────┘ (on failure)
```

1. **OBSERVE**: Inspect relevant context (screen state, active window, system status, user input) adaptively rather than continuously streaming.
2. **UNDERSTAND**: Parse context into structured representations (UI elements, window positions, process state).
3. **PLAN**: Formulate or refine concrete execution steps.
4. **ACT**: Execute authorized actions (launch app, input, terminal, filesystem).
5. **VERIFY**: Check post-action conditions to confirm the intended state was achieved.
6. **RECOVER**: If verification fails, diagnose the discrepancy and apply genuine recovery strategies or alternative plans.
7. **REMEMBER**: Persist relevant context, task history, and learned patterns to structured memory.

---

## 4. High-Level Architecture

JARVIS OS is structured in modular layers:

```
┌────────────────────────────────────────────────────────┐
│                   USER INTERFACES                      │
│   Text Input  •  Voice Input  •  Floating Orb / HUD    │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│                     JARVIS CORE                        │
│   • Input Ingestion & Task Manager                     │
│   • Agent Planner & Async Loop FSM                     │
│   • Skill & Tool Registry                              │
│   • Structured Memory (SQLite initially)               │
│   • Device Registry & Router                           │
│   • Permission & Action Logging System                 │
└──────────────────────────┬─────────────────────────────┘
                           │ WebSockets (Local / Auth)
┌──────────────────────────▼─────────────────────────────┐
│               AUTHORIZED DEVICE AGENTS                 │
│  ┌─────────────────────────┐ ┌──────────────────────┐  │
│  │      Windows Agent      │ │ Future iPad Companion│  │
│  │ • Screen Observation    │ │ • Status Relay       │  │
│  │ • Window & App Control  │ │ • Notifications      │  │
│  │ • Input & Automation    │ │ • Approved Shortcuts │  │
│  │ • Process & Filesystem  │ │   (Within iPadOS)    │  │
│  └─────────────────────────┘ └──────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 5. Development Philosophy & Rules

- **Incremental & Verified**: Every stage is implemented in isolation, covered by automated tests, verified, and committed before moving to the next.
- **Single Source of Truth**: The authoritative Git repository is [Senseify/JARVIS](https://github.com/Senseify/JARVIS). All code, configuration, documentation, and tests reside here.
- **No Fabrications**: Features are only reported as working when validated by actual tests.
- **Strict Boundary Integrity**: No project-specific assumptions or hard-coded application hooks.

---

## 6. Runtime & Environment Requirements

- **Python Version**: `>=3.11, <3.14` (Recommended: **Python 3.12** for optimal ecosystem and wheel stability).
- **Core Stack**: FastAPI, Uvicorn, Pydantic v2, SQLite, Pytest, WebSockets.
- **Product Web Interface**: Vanilla HTML5, CSS3, and ES6 JavaScript with dark cinematic HUD aesthetic (Zero frontend build tools required to run).

---

## 7. Local-First AI Reasoning (No API Key Required)

JARVIS OS is designed from the ground up to operate **without any mandatory commercial API keys**:

1. **Embedded Deterministic Reasoner**: Out of the box, JARVIS runs with an embedded zero-dependency local reasoner that extracts structured multi-step desktop automation plans and answers conversational queries instantly.
2. **Local Model Servers (Ollama, llama.cpp, vLLM)**:
   - Install Ollama from [ollama.ai](https://ollama.ai).
   - Download and run an open-weight model:
     ```bash
     ollama run llama3.2:latest
     ```
   - JARVIS Core automatically connects to `http://localhost:11434/v1` via `LocalModelProvider`.
   - Switch active provider via `POST /ai/models/select?name=ollama_local` or directly through the UI.

---

## 8. Launching JARVIS OS & Web Interface

1. **Install Dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

2. **Start JARVIS Core**:
   ```bash
   python -m core.main
   ```
   Or:
   ```bash
   uvicorn core.main:app --host 127.0.0.1 --port 8000
   ```

3. **Access the Product Web Interface**:
   Open `http://localhost:8000/` or `http://localhost:8000/ui/` in any modern browser.
   - **Persistent Dynamic Orb**: Real-time visualization of agent states (`IDLE`, `THINKING`, `PLANNING`, `ACTING`, `VERIFYING`, `RECOVERING`, `SUCCESS`, `ERROR`).
   - **Virtual Cursor Overlay**: Displays target coordinate markers and element bounding highlights during desktop automation.
   - **Live Telemetry Timeline**: Streams real-time thoughts, plan steps, and verification receipts.

---

## 9. Running Automated Tests

Run the full deterministic test suite:
```bash
pytest
```
To run specific subsystems:
```bash
pytest tests/test_ai_runtime.py
pytest tests/test_security_policy.py
pytest tests/test_planner_recovery.py
pytest tests/test_e2e_intelligence.py
```

