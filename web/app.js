// JARVIS OS — Real-Time Web Client & Orb HUD Visualizer

const state = {
  ws: null,
  sessionId: "web-session-" + Math.random().toString(36).substring(2, 8),
  currentPlan: null,
};

// DOM Elements
const orbEl = document.getElementById("jarvisOrb");
const orbStateText = document.getElementById("orbStateText");
const orbDetailText = document.getElementById("orbDetailText");
const wsDot = document.getElementById("wsDot");
const statusWs = document.getElementById("statusWs");
const statusModel = document.getElementById("statusModel");
const statusDevice = document.getElementById("statusDevice");
const timelineFeed = document.getElementById("timelineFeed");
const chatForm = document.getElementById("chatForm");
const promptInput = document.getElementById("promptInput");
const btnSend = document.getElementById("btnSend");
const btnMic = document.getElementById("btnMic");
const btnRefreshStatus = document.getElementById("btnRefreshStatus");
const btnClearFeed = document.getElementById("btnClearFeed");
const cursorCrosshair = document.getElementById("cursorCrosshair");
const cursorCoords = document.getElementById("cursorCoords");
const planStepsList = document.getElementById("planStepsList");

// 1. WebSocket Event Stream
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/events`;

  statusWs.innerHTML = '<span class="dot connecting" id="wsDot"></span> Stream: Connecting';
  state.ws = new WebSocket(wsUrl);

  state.ws.onopen = () => {
    statusWs.innerHTML = '<span class="dot online" id="wsDot"></span> Stream: Active';
    appendTimeline("system", "Real-time telemetry stream connected to JARVIS Core.");
  };

  state.ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleRuntimeEvent(data);
    } catch (err) {
      console.error("Failed to parse websocket event:", err);
    }
  };

  state.ws.onclose = () => {
    statusWs.innerHTML = '<span class="dot" id="wsDot"></span> Stream: Disconnected';
    setTimeout(connectWebSocket, 3000);
  };

  state.ws.onerror = () => {
    state.ws.close();
  };
}

// 2. Event Handler: Reflect genuine runtime state
function handleRuntimeEvent(agentEvent) {
  const type = agentEvent.event_type;
  const payload = agentEvent.payload || {};

  switch (type) {
    case "orb_state_changed":
      setOrbState(payload.state, payload.detail);
      break;

    case "virtual_cursor_moved":
      updateVirtualCursor(payload.x, payload.y, payload.action);
      break;

    case "plan_created":
      renderPlan(payload);
      break;

    case "plan_step_started":
      updateStepStatus(payload.step_id, "running");
      break;

    case "plan_step_verifying":
      updateStepStatus(payload.step_id, "verifying");
      break;

    case "plan_step_completed":
      updateStepStatus(payload.step_id, "completed");
      break;

    case "plan_step_failed":
      updateStepStatus(payload.step_id, "failed");
      break;

    case "plan_completed":
      setOrbState("success", "Execution completed successfully");
      break;

    case "voice_command_received":
      appendTimeline("system", `Voice input received: "${payload.transcript || ""}"`);
      break;

    case "voice_command_response_ready":
      if (payload.response_text) {
        appendTimeline("assistant", `[Spoken] ${payload.response_text}`);
      }
      break;

    default:
      break;
  }
}

// 3. Orb State Controller
function setOrbState(stateName, detail = "") {
  if (!orbEl) return;
  const validStates = ["idle", "thinking", "planning", "acting", "verifying", "recovering", "success", "error"];
  validStates.forEach((s) => orbEl.classList.remove(s));

  const active = validStates.includes(stateName) ? stateName : "idle";
  orbEl.classList.add(active);

  orbStateText.textContent = `SYSTEM ${active.toUpperCase()}`;
  if (detail) {
    orbDetailText.textContent = detail;
  }
}

// 4. Virtual Cursor Overlay
function updateVirtualCursor(x, y, action = "Target") {
  if (!cursorCrosshair) return;
  cursorCrosshair.style.display = "block";
  // Map coordinates proportionally inside target card area
  const area = document.getElementById("cursorTargetArea");
  const rect = area.getBoundingClientRect();

  // Screen virtual coordinate normalized to card display
  const normX = Math.min(Math.max((x % 1920) / 1920, 0.1), 0.9) * rect.width;
  const normY = Math.min(Math.max((y % 1080) / 1080, 0.1), 0.9) * rect.height;

  cursorCrosshair.style.left = `${normX}px`;
  cursorCrosshair.style.top = `${normY}px`;
  cursorCoords.textContent = `X: ${x} | Y: ${y} (${action})`;
}

// 5. Multi-Step Plan Rendering
function renderPlan(payload) {
  if (!planStepsList) return;
  planStepsList.innerHTML = "";

  const stepsCount = payload.steps_count || 1;
  for (let i = 1; i <= stepsCount; i++) {
    const div = document.createElement("div");
    div.className = "step-item";
    div.id = `stepItem-${i}`;
    div.innerHTML = `
      <span class="step-name">Step ${i}: Action</span>
      <span class="step-status-badge pending" id="stepBadge-${i}">Pending</span>
    `;
    planStepsList.appendChild(div);
  }
}

function updateStepStatus(stepId, status) {
  const badges = document.querySelectorAll(".step-status-badge");
  if (badges.length > 0) {
    const badge = badges[0];
    badge.className = `step-status-badge ${status}`;
    badge.textContent = status.toUpperCase();
  }
}

// 6. Feed / Timeline
function appendTimeline(role, text) {
  const entry = document.createElement("div");
  entry.className = `timeline-entry ${role}`;

  const timeStr = new Date().toLocaleTimeString();
  const roleLabel = role.toUpperCase();

  entry.innerHTML = `
    <div class="entry-header">
      <span class="${role === "system" ? "badge-sys" : ""}">${roleLabel}</span>
      <span class="time">${timeStr}</span>
    </div>
    <div class="entry-content">${escapeHtml(text)}</div>
  `;

  timelineFeed.appendChild(entry);
  timelineFeed.scrollTop = timelineFeed.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// 7. Prompt Submission
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = promptInput.value.trim();
  if (!text) return;

  promptInput.value = "";
  appendTimeline("user", text);
  setOrbState("thinking", "Analyzing natural language request...");

  try {
    const res = await fetch("/ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        session_id: state.sessionId,
      }),
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || "Request failed");
    }

    const data = await res.json();
    appendTimeline("assistant", data.message);
    if (!data.requires_action) {
      setOrbState("idle", "Ready");
    }
  } catch (err) {
    appendTimeline("system", `Execution error: ${err.message}`);
    setOrbState("error", err.message);
  }
});

// 8. Microphone / Voice Command Trigger
btnMic.addEventListener("click", async () => {
  const sample = prompt("Enter voice command text simulation:", "Open Notepad and type hello world");
  if (sample) {
    appendTimeline("user", `[Voice Input] ${sample}`);
    try {
      const res = await fetch("/voice/command/text?text=" + encodeURIComponent(sample), {
        method: "POST",
      });
      const data = await res.json();
      appendTimeline("assistant", data.response_text);
    } catch (err) {
      appendTimeline("system", `Voice error: ${err.message}`);
    }
  }
});

// 9. Diagnostics Refresh
async function refreshDiagnostics() {
  try {
    const res = await fetch("/system/status");
    if (!res.ok) return;
    const data = await res.json();

    if (statusModel && data.model_runtime) {
      statusModel.innerHTML = `<span class="dot online"></span> Model: ${data.model_runtime.model_id}`;
    }
    if (statusDevice && data.connected_agents) {
      const count = data.connected_agents.length;
      statusDevice.innerHTML = `<span class="dot ${count > 0 ? "online" : ""}"></span> Agents: ${count} connected`;
    }
  } catch (err) {
    console.error("Diagnostic error:", err);
  }
}

btnRefreshStatus.addEventListener("click", refreshDiagnostics);
btnClearFeed.addEventListener("click", () => {
  timelineFeed.innerHTML = "";
  appendTimeline("system", "Timeline cleared.");
});

// Initialize on page load
window.addEventListener("DOMContentLoaded", () => {
  connectWebSocket();
  refreshDiagnostics();
});
