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
- **Core Stack**: FastAPI, Uvicorn, Pydantic v2, SQLite, Pytest.
- **Future UI Stack**: Tauri, React, TypeScript, Tailwind.
