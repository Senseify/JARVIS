/**
 * JARVIS OS — Spatial Intelligence Operating Environment Client (app.js)
 *
 * Connects the Three.js Spatial Orb, HUD Telemetry, Targeting Reticle,
 * Navigation Rail, Command Deck, and Chat Workspace to the live
 * FastAPI Core runtime and WebSocket event stream.
 */

(function () {
  'use strict';

  // State Management
  const state = {
    currentTab: 'spatial-all',
    spatialMode: 'HOME', // 'HOME' | 'CHAT'
    coreStatus: 'offline',
    wsConnected: false,
    activeModel: 'Deterministic Local',
    activeEngine: 'in-process',
    deviceProfile: null,
    memoryCount: 0,
    chatMessages: [],
    audioActive: false,
    audioContext: null,
    analyser: null,
    audioDataArray: null,
    lastLatencyMs: 0.0,
  };

  // DOM Cache
  const DOM = {};

  function cacheDOMElements() {
    DOM.viewport = document.getElementById('spatialViewport');
    DOM.coreLoopState = document.getElementById('coreLoopState');
    DOM.topbarModelName = document.getElementById('topbarModelName');
    DOM.topbarDeviceType = document.getElementById('topbarDeviceType');
    DOM.wsDot = document.getElementById('wsDot');
    DOM.wsStatusText = document.getElementById('wsStatusText');
    DOM.deviceMeta = document.getElementById('deviceMeta');

    // Subsystem Cells
    DOM.valAiStatus = document.getElementById('valAiStatus');
    DOM.valModelBackend = document.getElementById('valModelBackend');
    DOM.valLocalModelName = document.getElementById('valLocalModelName');
    DOM.valModelEngine = document.getElementById('valModelEngine');
    DOM.valDeviceArch = document.getElementById('valDeviceArch');
    DOM.valDeviceGpu = document.getElementById('valDeviceGpu');
    DOM.valMemCount = document.getElementById('valMemCount');
    DOM.valLatency = document.getElementById('valLatency');
    DOM.gaugeLatencyFill = document.getElementById('gaugeLatencyFill');

    // Targeting Reticle
    DOM.cursorTargetArea = document.getElementById('cursorTargetArea');
    DOM.cursorCrosshair = document.getElementById('cursorCrosshair');
    DOM.crosshairLabel = document.getElementById('crosshairLabel');
    DOM.cursorIdlePrompt = document.getElementById('cursorIdlePrompt');
    DOM.cursorCoords = document.getElementById('cursorCoords');
    DOM.cursorAction = document.getElementById('cursorAction');

    // Workspace & Chat
    DOM.centralWorkspace = document.getElementById('centralWorkspace');
    DOM.workspaceScrollArea = document.getElementById('workspaceScrollArea');
    DOM.centerpieceSection = document.getElementById('centerpieceSection');
    DOM.commandDeck = document.getElementById('commandDeck');
    DOM.commandDeckTitle = document.getElementById('commandDeckTitle');
    DOM.chatForm = document.getElementById('chatForm');
    DOM.promptInput = document.getElementById('promptInput');
    DOM.btnSend = document.getElementById('btnSend');
    DOM.btnMic = document.getElementById('btnMic');

    // Timeline & Plan
    DOM.planStepsList = document.getElementById('planStepsList');
    DOM.planIdBadge = document.getElementById('planIdBadge');
    DOM.timelineFeed = document.getElementById('timelineFeed');
    DOM.btnRefreshStatus = document.getElementById('btnRefreshStatus');
    DOM.btnClearFeed = document.getElementById('btnClearFeed');

    // Audio Canvas
    DOM.audioWaveCanvas = document.getElementById('audioWaveCanvas');

    // Nav Rail
    DOM.navItems = document.querySelectorAll('.nav-rail-item');
    DOM.chips = document.querySelectorAll('.tactical-chip');
  }

  // -------------------------------------------------------------------------
  // OrbState Normalizer: maps backend OrbState enum values to orb.js keys
  // Backend: idle, listening, thinking, planning, acting, verifying, recovering, success, error
  // Orb.js:  IDLE, LISTENING, UNDERSTAND, PLAN, ACT, VERIFY, RECOVER, SUCCESS, ERROR + OBSERVE, REMEMBER, SPEAKING
  // -------------------------------------------------------------------------
  const ORB_STATE_MAP = {
    idle: 'IDLE',
    listening: 'LISTENING',
    thinking: 'UNDERSTAND',    // ReasoningEngine thinking → UNDERSTAND visual
    planning: 'PLAN',          // Planner running → PLAN visual
    acting: 'ACT',             // Tool execution → ACT visual
    verifying: 'VERIFY',       // Verification → VERIFY visual
    recovering: 'RECOVER',     // RecoveryEngine → RECOVER visual
    success: 'SUCCESS',
    error: 'ERROR',
    // Frontend-driven (already uppercase):
    observe: 'OBSERVE',
    understand: 'UNDERSTAND',
    plan: 'PLAN',
    act: 'ACT',
    verify: 'VERIFY',
    recover: 'RECOVER',
    remember: 'REMEMBER',
    speaking: 'SPEAKING',
  };

  function normalizeOrbState(raw) {
    if (!raw) return 'IDLE';
    const lower = raw.toLowerCase();
    return ORB_STATE_MAP[lower] || raw.toUpperCase();
  }

  // -------------------------------------------------------------------------
  // Three.js Orb Initialization
  // -------------------------------------------------------------------------
  function initOrb() {
    if (window.initJarvisOrb) {
      window.initJarvisOrb('threeOrbContainer');
      window.setJarvisOrbState('IDLE');
    }
  }

  // -------------------------------------------------------------------------
  // WebSocket Event Stream Bridge
  // -------------------------------------------------------------------------
  function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/events`;

    DOM.wsStatusText.textContent = 'CONNECTING';
    DOM.wsDot.className = 'node-indicator connecting';

    let socket;
    try {
      socket = new WebSocket(wsUrl);
    } catch (e) {
      console.warn('WebSocket connection failed:', e);
      DOM.wsStatusText.textContent = 'STANDBY';
      DOM.wsDot.className = 'node-indicator standby';
      return;
    }

    socket.onopen = function () {
      state.wsConnected = true;
      DOM.wsStatusText.textContent = 'STREAMING';
      DOM.wsDot.className = 'node-indicator online';
      logTimeline('STREAM', 'WebSocket telemetry stream synchronized with Core runtime.');
    };

    socket.onmessage = function (event) {
      try {
        const payload = JSON.parse(event.data);
        handleAgentEvent(payload);
      } catch (e) {
        console.error('Error parsing event message:', e);
      }
    };

    socket.onclose = function () {
      state.wsConnected = false;
      DOM.wsStatusText.textContent = 'RECONNECTING';
      DOM.wsDot.className = 'node-indicator connecting';
      setTimeout(initWebSocket, 3000);
    };

    socket.onerror = function () {
      DOM.wsStatusText.textContent = 'STANDBY';
      DOM.wsDot.className = 'node-indicator standby';
    };
  }

  function handleAgentEvent(event) {
    const type = event.event_type;
    const data = event.payload || {};

    // 1. Core State & Orb Transitions
    // Backend emits 'orb_state_changed' from ReasoningEngine/RecoveryEngine
    if (type === 'orb_state_changed') {
      const orbState = normalizeOrbState(data.state || 'IDLE');
      window.setJarvisOrbState(orbState);
      updateOrbStateDisplay(orbState);
      if (data.detail) logTimeline('ORB', data.detail);
    }
    // Legacy alias
    if (type === 'state_transition') {
      const orbState = normalizeOrbState(data.to_state || data.state || 'IDLE');
      window.setJarvisOrbState(orbState);
      updateOrbStateDisplay(orbState);
      logTimeline('STATE', `Agent loop transitioned to ${orbState}`);
    }

    // 2. Reasoning loop events
    if (type === 'reasoning_started') {
      window.setJarvisOrbState('UNDERSTAND');
      updateOrbStateDisplay('UNDERSTAND');
    }
    if (type === 'reasoning_completed') {
      const ms = data.duration_ms ? `${Math.round(data.duration_ms)}ms` : '';
      logTimeline('THINK', `Reasoning completed${ms ? ' in ' + ms : ''}`);
    }

    // 3. Plan Created
    if (type === 'plan_created') {
      DOM.planIdBadge.textContent = data.plan_id ? `PLAN // ${data.plan_id.slice(-6)}` : 'PLAN // ACTIVE';
      renderPlanSteps(data.steps || [{ name: data.goal || 'Execution sequence', status: 'pending' }]);
      logTimeline('PLAN', `Plan constructed: "${data.goal}" (${data.steps_count || 1} steps)`);
      window.setJarvisOrbState('PLAN');
      updateOrbStateDisplay('PLAN');
    }

    // 4. Step & Tool Execution -> Reticle Updates
    if (type === 'plan_step_started' || type === 'action_started') {
      const toolName = data.tool || data.step_name || data.capability || 'action';
      updateReticleActive(toolName, data.parameters || data.arguments || {});
      window.setJarvisOrbState('ACT');
      updateOrbStateDisplay('ACT');
    }

    if (type === 'action_completed' || type === 'action_executed') {
      const tool = data.tool || data.capability || 'ACTION';
      const actionCoords = data.result?.coords || data.arguments || {};
      updateReticleActive(tool, actionCoords);
      logTimeline('ACT', `Executed ${tool} — status: ${data.verification_status || data.status || 'ok'}`);
    }

    // 5. Verification
    if (type === 'verification_completed' || type === 'verification_result') {
      const verified = data.success !== false && data.status !== 'failed';
      window.setJarvisOrbState(verified ? 'VERIFY' : 'RECOVER');
      updateOrbStateDisplay(verified ? 'VERIFY' : 'RECOVER');
      DOM.cursorAction.textContent = verified ? 'VERIFIED' : 'RETRY';
      DOM.cursorAction.style.color = verified ? 'var(--state-success)' : 'var(--state-warning)';
      logTimeline(verified ? 'VERIFY' : 'RECOVER', data.details || `Verification check ${verified ? 'passed' : 'failed'}`);
    }

    // 6. Memory Written
    if (type === 'memory_stored') {
      state.memoryCount++;
      DOM.valMemCount.textContent = `${state.memoryCount} ENTRIES`;
      logTimeline('REMEMBER', `Knowledge persisted: ${data.summary || 'Task outcome'}`);
    }

    // 7. Voice Events
    if (type === 'voice_command_received') {
      window.setJarvisOrbState('UNDERSTAND');
      updateOrbStateDisplay('UNDERSTAND');
      logTimeline('VOICE', `Transcript: "${data.transcript || ''}"`);
    }

    // 8. Plan/Recovery events
    if (type === 'recovery_started') {
      window.setJarvisOrbState('RECOVER');
      updateOrbStateDisplay('RECOVER');
      logTimeline('RECOVER', `Recovery triggered: ${data.reason || 'failure detected'}`);
    }

    // 9. Virtual cursor tracking
    if (type === 'virtual_cursor_moved') {
      updateReticleActive(data.action || 'MOVE', { x: data.x, y: data.y });
    }
  }

  function updateOrbStateDisplay(stateName) {
    const upper = (stateName || 'IDLE').toUpperCase();
    if (DOM.coreLoopState) DOM.coreLoopState.textContent = upper;
    const orbText = document.getElementById('orbStateText');
    if (orbText) orbText.textContent = `SYSTEM // ${upper}`;
  }

  // -------------------------------------------------------------------------
  // Spatial Targeting Reticle Controller
  // -------------------------------------------------------------------------
  function updateReticleActive(toolName, params) {
    DOM.cursorCrosshair.style.display = 'block';
    DOM.cursorIdlePrompt.style.display = 'none';

    let x = params.x !== undefined ? params.x : Math.floor(Math.random() * 800 + 200);
    let y = params.y !== undefined ? params.y : Math.floor(Math.random() * 500 + 150);

    DOM.cursorCoords.textContent = `X: ${x} | Y: ${y}`;
    DOM.cursorAction.textContent = toolName.toUpperCase();
    DOM.cursorAction.style.color = 'var(--cyan-bright)';
    DOM.crosshairLabel.textContent = `TARGET: ${toolName.toUpperCase()}`;

    // Position crosshair proportionally in the 220px preview area
    const normX = Math.min(Math.max((x / 1920) * 100, 10), 90);
    const normY = Math.min(Math.max((y / 1080) * 100, 10), 90);
    DOM.cursorCrosshair.style.left = `${normX}%`;
    DOM.cursorCrosshair.style.top = `${normY}%`;
  }

  function updateReticleIdle() {
    DOM.cursorCrosshair.style.display = 'none';
    DOM.cursorIdlePrompt.style.display = 'block';
    DOM.cursorCoords.textContent = 'X: -- | Y: --';
    DOM.cursorAction.textContent = 'STANDBY';
    DOM.cursorAction.style.color = 'var(--silver-medium)';
  }

  // -------------------------------------------------------------------------
  // Real System & Device Diagnostics Polling
  // -------------------------------------------------------------------------
  async function pollSystemDiagnostics() {
    const t0 = performance.now();
    try {
      const resp = await fetch('/system/status');
      const data = await resp.json();
      state.lastLatencyMs = round(performance.now() - t0, 1);

      // 1. Latency Bar
      DOM.valLatency.textContent = `${state.lastLatencyMs} ms`;
      const gaugeWidth = Math.min(Math.max((state.lastLatencyMs / 50) * 100, 8), 100);
      DOM.gaugeLatencyFill.style.width = `${gaugeWidth}%`;

      // 2. Memory Count
      if (data.memory && data.memory.total_entries !== undefined) {
        state.memoryCount = data.memory.total_entries;
        DOM.valMemCount.textContent = `${state.memoryCount} ENTRIES`;
      }

      // 3. Model & Engine Telemetry
      const mi = data.model_intelligence;
      if (mi) {
        state.activeModel = mi.active_model_id || 'Deterministic Local';
        state.activeEngine = mi.active_engine || 'in-process';

        if (DOM.topbarModelName) DOM.topbarModelName.textContent = state.activeModel.toUpperCase();
        if (DOM.valLocalModelName) DOM.valLocalModelName.textContent = state.activeModel;
        if (DOM.valModelEngine) {
          const engineLabel = state.activeEngine.replace('_', ' ').toUpperCase();
          const modelCount = mi.registered_models_count || 1;
          DOM.valModelEngine.textContent = `${engineLabel} // ${modelCount} MODELS`;
        }
        if (DOM.valAiStatus) {
          DOM.valAiStatus.textContent = state.activeEngine === 'deterministic_embedded' ? 'LOCAL RULE-BASED' : 'LOCAL LLM ACTIVE';
        }
        if (DOM.valModelBackend) {
          DOM.valModelBackend.textContent = mi.active_provider || 'deterministic';
        }

        const sbRouted = document.getElementById('sbRoutedModel');
        if (sbRouted) sbRouted.textContent = mi.active_model_id;
      }

      // 4. Device Hub Hardware Specs — from device_hub nested object in system/status
      const dh = data.device_hub;
      if (dh) {
        state.deviceProfile = dh;
        const osArch = `${(dh.os_type || 'unknown').toUpperCase()} ${(dh.architecture || '').toUpperCase()}`;
        if (DOM.valDeviceArch) DOM.valDeviceArch.textContent = osArch;
        if (DOM.topbarDeviceType) DOM.topbarDeviceType.textContent = (dh.device_name || 'LOCAL HOST').toUpperCase();

        const gpus = dh.gpus || [];
        const gpuInfo = gpus[0]
          ? `${(gpus[0].backend || 'cpu').toUpperCase()} ${gpus[0].is_integrated ? '(UMA)' : 'GPU'}`
          : 'CPU ONLY';
        if (DOM.valDeviceGpu) DOM.valDeviceGpu.textContent = gpuInfo;
        if (DOM.deviceMeta) {
          const ramGb = dh.ram_total_mb ? `${(dh.ram_total_mb / 1024).toFixed(0)}GB RAM` : '';
          DOM.deviceMeta.textContent = `${dh.cpu_model || 'CPU'} // ${ramGb} // ${osArch}`;
        }
      }
    } catch (e) {
      console.warn('System diagnostics poll failed:', e);
      DOM.valLatency.textContent = 'ERR';
    }
  }

  // -------------------------------------------------------------------------
  // Spatial HOME <-> CHAT Mode Controller
  // -------------------------------------------------------------------------
  function setSpatialMode(mode) {
    state.spatialMode = mode;
    if (window.setJarvisSpatialMode) {
      window.setJarvisSpatialMode(mode);
    }

    if (mode === 'CHAT') {
      DOM.viewport.classList.add('mode-chat');
      DOM.viewport.classList.remove('mode-home');
      DOM.centralWorkspace.style.display = 'flex';
      renderChatWorkspace();
      DOM.promptInput.focus();
    } else {
      DOM.viewport.classList.add('mode-home');
      DOM.viewport.classList.remove('mode-chat');
      DOM.centralWorkspace.style.display = 'none';
    }
  }

  // -------------------------------------------------------------------------
  // Chat Workspace View & Submission
  // -------------------------------------------------------------------------
  function renderChatWorkspace() {
    if (!DOM.workspaceScrollArea) return;
    DOM.workspaceScrollArea.innerHTML = '';

    if (state.chatMessages.length === 0) {
      const welcome = document.createElement('div');
      welcome.className = 'chat-bubble assistant';
      welcome.innerHTML = `
        <div class="chat-meta">JARVIS CORE // INTELLIGENCE WORKSPACE</div>
        <div>Systems initialized and operational. You are in direct conversation mode with the autonomous reasoning loop. How may I assist you today?</div>
      `;
      DOM.workspaceScrollArea.appendChild(welcome);
      return;
    }

    state.chatMessages.forEach((msg) => {
      const bubble = document.createElement('div');
      bubble.className = `chat-bubble ${msg.role}`;
      let receiptsHtml = '';
      if (msg.receipt) {
        receiptsHtml = `<div class="chat-receipt">${msg.receipt}</div>`;
      }
      bubble.innerHTML = `
        <div class="chat-meta">${msg.role === 'user' ? 'OPERATOR' : 'JARVIS // ' + (msg.model || state.activeModel).toUpperCase()}</div>
        <div>${escapeHtml(msg.text)}</div>
        ${receiptsHtml}
      `;
      DOM.workspaceScrollArea.appendChild(bubble);
    });

    DOM.workspaceScrollArea.scrollTop = DOM.workspaceScrollArea.scrollHeight;
  }

  async function handleCommandSubmit(e) {
    if (e) e.preventDefault();
    const prompt = DOM.promptInput.value.trim();
    if (!prompt) return;

    DOM.promptInput.value = '';

    // Add user message to state
    state.chatMessages.push({ role: 'user', text: prompt, timestamp: new Date() });

    // Transition to CHAT mode if on HOME
    if (state.spatialMode !== 'CHAT') {
      switchTab('spatial-chat');
    } else {
      renderChatWorkspace();
    }

    // Trigger Orb State Sequence: OBSERVE -> UNDERSTAND -> PLAN
    window.setJarvisOrbState('OBSERVE');
    logTimeline('USER', prompt);

    try {
      window.setJarvisOrbState('UNDERSTAND');
      const resp = await fetch('/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: prompt, session_id: 'spatial-hud' }),
      });

      const data = await resp.json();

      if (data.requires_action) {
        window.setJarvisOrbState('ACT');
        logTimeline('ACT', `Action sequence completed via ${data.model_used}`);
      }

      window.setJarvisOrbState('SUCCESS');

      state.chatMessages.push({
        role: 'assistant',
        text: data.message || 'Action executed successfully.',
        model: data.model_used || state.activeModel,
        receipt: data.requires_action ? `Action verified in ${round(data.duration_ms, 1)}ms` : null,
      });

      renderChatWorkspace();
      setTimeout(() => window.setJarvisOrbState('IDLE'), 3500);
      pollSystemDiagnostics();
    } catch (err) {
      window.setJarvisOrbState('ERROR');
      state.chatMessages.push({
        role: 'assistant',
        text: `Execution failed: ${err.message}`,
        model: 'ERROR',
      });
      renderChatWorkspace();
      setTimeout(() => window.setJarvisOrbState('IDLE'), 3000);
    }
  }

  // -------------------------------------------------------------------------
  // Real Web Audio Microphone Waveform Visualizer
  // -------------------------------------------------------------------------
  async function toggleMicrophone() {
    if (state.audioActive) {
      stopAudioCapture();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      state.analyser = state.audioContext.createAnalyser();
      state.analyser.fftSize = 64;

      const source = state.audioContext.createMediaStreamSource(stream);
      source.connect(state.analyser);

      state.audioDataArray = new Uint8Array(state.analyser.frequencyBinCount);
      state.audioActive = true;
      DOM.btnMic.classList.add('active');
      window.setJarvisOrbState('LISTENING');
      drawAudioWaveform();
    } catch (e) {
      console.warn('Microphone access denied or unavailable:', e);
      // Fallback pulse on button
      DOM.btnMic.classList.add('pulse');
      setTimeout(() => DOM.btnMic.classList.remove('pulse'), 1200);
    }
  }

  function stopAudioCapture() {
    state.audioActive = false;
    DOM.btnMic.classList.remove('active');
    if (state.audioContext) {
      state.audioContext.close();
      state.audioContext = null;
    }
    window.setJarvisOrbState('IDLE');
  }

  function drawAudioWaveform() {
    if (!state.audioActive || !DOM.audioWaveCanvas) return;
    requestAnimationFrame(drawAudioWaveform);

    const canvas = DOM.audioWaveCanvas;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    state.analyser.getByteFrequencyData(state.audioDataArray);

    ctx.clearRect(0, 0, width, height);
    const barWidth = (width / state.audioDataArray.length) * 2;
    let x = 0;

    for (let i = 0; i < state.audioDataArray.length; i++) {
      const barHeight = (state.audioDataArray[i] / 255) * height;
      ctx.fillStyle = `rgba(0, 229, 255, ${Math.max(0.2, barHeight / height)})`;
      ctx.fillRect(x, height - barHeight, barWidth - 1, barHeight);
      x += barWidth;
    }
  }

  // -------------------------------------------------------------------------
  // View Router (HOME, CHAT, TASKS, MEMORY, DEVICES, SKILLS, SYSTEM)
  // -------------------------------------------------------------------------
  function switchTab(tabId) {
    state.currentTab = tabId;

    DOM.navItems.forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
    });

    if (tabId === 'spatial-all') {
      setSpatialMode('HOME');
      return;
    }

    if (tabId === 'spatial-chat') {
      setSpatialMode('CHAT');
      return;
    }

    // For other tabs, dock Orb and render view into central workspace
    setSpatialMode('CHAT');
    renderSpecializedView(tabId);
  }

  async function renderSpecializedView(tabId) {
    if (!DOM.workspaceScrollArea) return;
    DOM.workspaceScrollArea.innerHTML = '<div class="chat-meta">LOADING VIEW METRICS...</div>';

    if (tabId === 'spatial-tasks') {
      try {
        const res = await fetch('/tasks');
        const tasks = await res.json();
        let html = '<div class="chat-meta">TASK MANAGER // ACTIVE GRAPHS</div>';
        if (tasks.length === 0) {
          html += '<div class="chat-bubble assistant">No background tasks currently queued.</div>';
        } else {
          tasks.forEach((t) => {
            html += `
              <div class="chat-bubble assistant">
                <div class="chat-meta">TASK // ${t.id.slice(0, 8)} | STATE: ${t.state}</div>
                <div>${escapeHtml(t.input)}</div>
              </div>
            `;
          });
        }
        DOM.workspaceScrollArea.innerHTML = html;
      } catch (e) {
        DOM.workspaceScrollArea.innerHTML = `<div class="chat-bubble assistant">Failed to load tasks: ${e.message}</div>`;
      }
    } else if (tabId === 'spatial-memory') {
      try {
        const res = await fetch('/system/status');
        const data = await res.json();
        let html = `
          <div class="chat-meta">PERSISTENT MEMORY // SQLITE ENGINE</div>
          <div class="chat-bubble assistant">
            <div><strong>Active Memory Storage:</strong> SQLite (Deduplicated & Persistent)</div>
            <div><strong>Total Persisted Entries:</strong> ${data.memory?.total_entries || 0}</div>
            <div><strong>Subsystem State:</strong> Operational</div>
          </div>
        `;
        DOM.workspaceScrollArea.innerHTML = html;
      } catch (e) {
        DOM.workspaceScrollArea.innerHTML = `<div class="chat-bubble assistant">Memory query failed: ${e.message}</div>`;
      }
    } else if (tabId === 'spatial-devices') {
      try {
        const res = await fetch('/api/v1/devices/status');
        const dev = await res.json();
        let gpusHtml = dev.gpus?.map((g) => `<li>${g.name} (${g.backend.toUpperCase()} - ${g.vram_total_mb} MB)</li>`).join('') || 'None';
        let html = `
          <div class="chat-meta">DEVICE HUB // HARDWARE CAPABILITY PROBE</div>
          <div class="chat-bubble assistant">
            <div><strong>Host Identifier:</strong> ${dev.device_id}</div>
            <div><strong>Operating System:</strong> ${dev.os_type} ${dev.architecture} (${dev.os_release})</div>
            <div><strong>CPU Processor:</strong> ${dev.cpu_model} (${dev.cpu_cores_logical} logical / ${dev.cpu_cores_physical} physical cores)</div>
            <div><strong>System RAM:</strong> ${dev.ram_total_mb} MB Total | ${dev.ram_available_mb} MB Free</div>
            <div><strong>Storage:</strong> ${dev.storage_free_gb} GB free of ${dev.storage_total_gb} GB</div>
            <div><strong>Detected GPUs:</strong></div>
            <ul style="margin-left: 20px;">${gpusHtml}</ul>
            <div><strong>Supported Capabilities:</strong> ${dev.supported_features?.join(', ')}</div>
          </div>
        `;
        DOM.workspaceScrollArea.innerHTML = html;
      } catch (e) {
        DOM.workspaceScrollArea.innerHTML = `<div class="chat-bubble assistant">Device probe failed: ${e.message}</div>`;
      }
    } else if (tabId === 'spatial-skills') {
      try {
        const res = await fetch('/system/status');
        const data = await res.json();
        const skills = data.available_skills || ['launch_and_verify', 'click_and_verify', 'type_and_verify'];
        let html = `
          <div class="chat-meta">SKILLS ENGINE // REUSABLE DETERMINISTIC WORKFLOWS</div>
          <div class="chat-bubble assistant">
            <div><strong>Registered Skills (${skills.length}):</strong></div>
            <ul style="margin-left: 20px; margin-top: 6px;">
              ${skills.map((s) => `<li><code>${s}</code> — Verified multi-step workflow</li>`).join('')}
            </ul>
          </div>
        `;
        DOM.workspaceScrollArea.innerHTML = html;
      } catch (e) {
        DOM.workspaceScrollArea.innerHTML = `<div class="chat-bubble assistant">Skills query failed: ${e.message}</div>`;
      }
    } else if (tabId === 'spatial-system') {
      try {
        const res = await fetch('/system/security/policy');
        const pol = await res.json();
        let html = `
          <div class="chat-meta">SYSTEM POLICY // ZERO-SHELL SECURITY MATRIX</div>
          <div class="chat-bubble assistant">
            <div><strong>Security Tier:</strong> STRICT ALLOWLIST // RESTRICTED</div>
            <div><strong>Arbitrary Shell Execution:</strong> FORBIDDEN</div>
            <div><strong>Allowlisted Applications:</strong> ${pol.allowlisted_apps?.join(', ')}</div>
            <div><strong>Max Typing Length:</strong> ${pol.max_typing_length} chars</div>
            <div><strong>Remote Control:</strong> ${pol.allow_remote_control ? 'Authorized' : 'Restricted'}</div>
          </div>
        `;
        DOM.workspaceScrollArea.innerHTML = html;
      } catch (e) {
        DOM.workspaceScrollArea.innerHTML = `<div class="chat-bubble assistant">System policy query failed: ${e.message}</div>`;
      }
    }
  }

  // -------------------------------------------------------------------------
  // Helpers & Timeline Logging
  // -------------------------------------------------------------------------
  function renderPlanSteps(steps) {
    if (!DOM.planStepsList) return;
    DOM.planStepsList.innerHTML = '';
    steps.forEach((step, idx) => {
      const item = document.createElement('div');
      item.className = `plan-step-item ${step.status || 'pending'}`;
      item.innerHTML = `
        <span class="step-num">0${idx + 1}</span>
        <span class="step-desc">${escapeHtml(step.name || step.tool || 'Step')}</span>
        <span class="step-dot"></span>
      `;
      DOM.planStepsList.appendChild(item);
    });
  }

  function logTimeline(tag, message) {
    if (!DOM.timelineFeed) return;
    const entry = document.createElement('div');
    entry.className = 'timeline-entry system';
    const timeStr = new Date().toTimeString().split(' ')[0];
    entry.innerHTML = `
      <div class="entry-meta">
        <span class="badge-tag sys">${escapeHtml(tag)}</span>
        <span class="entry-timestamp">${timeStr}</span>
      </div>
      <div class="entry-body">${escapeHtml(message)}</div>
    `;
    DOM.timelineFeed.prepend(entry);
  }

  function round(val, dec) {
    return Number(Math.round(val + 'e' + dec) + 'e-' + dec);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // -------------------------------------------------------------------------
  // Boot Sequence
  // -------------------------------------------------------------------------
  window.addEventListener('DOMContentLoaded', () => {
    cacheDOMElements();
    initOrb();
    initWebSocket();
    pollSystemDiagnostics();
    setInterval(pollSystemDiagnostics, 10000);

    // Event Listeners
    if (DOM.chatForm) DOM.chatForm.addEventListener('submit', handleCommandSubmit);
    if (DOM.btnMic) DOM.btnMic.addEventListener('click', toggleMicrophone);
    if (DOM.btnRefreshStatus) DOM.btnRefreshStatus.addEventListener('click', pollSystemDiagnostics);
    if (DOM.btnClearFeed) DOM.btnClearFeed.addEventListener('click', () => (DOM.timelineFeed.innerHTML = ''));

    // Nav Rail
    DOM.navItems.forEach((btn) => {
      btn.addEventListener('click', () => {
        const tabId = btn.getAttribute('data-tab');
        switchTab(tabId);
      });
    });

    // Quick Command Chips
    DOM.chips.forEach((chip) => {
      chip.addEventListener('click', () => {
        const cmd = chip.getAttribute('data-cmd');
        if (cmd) {
          DOM.promptInput.value = cmd;
          handleCommandSubmit();
        }
      });
    });
  });
})();
