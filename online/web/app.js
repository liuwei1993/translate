const status = document.querySelector("#status");
const panels = {
  ready: document.querySelector("#panel-ready"),
  listening: document.querySelector("#panel-listening"),
  mic: document.querySelector("#panel-mic"),
  down: document.querySelector("#panel-down"),
  history: document.querySelector("#panel-history"),
};
const readyError = document.querySelector("#ready-error");
const liveSource = document.querySelector("#live-source");
const liveTranslation = document.querySelector("#live-translation");
const historyList = document.querySelector("#history");
const downHistory = document.querySelector("#down-history");
const sessionListWrap = document.querySelector("#session-list-wrap");
const sessionList = document.querySelector("#session-list");
const sessionDetail = document.querySelector("#session-detail");
const sessionMeta = document.querySelector("#session-meta");
const sessionLines = document.querySelector("#session-lines");
const historyEmpty = document.querySelector("#history-empty");

const STORAGE_KEY = "univoice.sessions";
const SESSION_LIMIT = 40;
let historyReturn = "ready";
let openSessionId = null;

let socket = null;
let mode = "auto";
let mediaStream = null;
let audioContext = null;
let workletNode = null;
let wakeLock = null;
let stopping = false;
let live = blank();
let history = [];

const MODES = {
  auto: "中英文互译",
  en: "中文 → 英文",
  zh: "英文 → 中文",
  "ja-auto": "中日互译",
  ja: "中文 → 日文",
  ja2zh: "日文 → 中文",
};
const LEADS = {
  auto: "说中文就出英文，说英文就出中文。",
  en: "只把中文译成英文。",
  zh: "只把英文译成中文。",
  "ja-auto": "说中文就出日文，说日文就出中文。",
  ja: "只把中文译成日文。",
  ja2zh: "只把日文译成中文。",
};
const directionToggle = document.querySelector("#direction-toggle");
const directionMenu = document.querySelector("#direction-menu");
const directionLabel = document.querySelector("#direction-label");
const lead = document.querySelector("#lead");

function startMessage() {
  return JSON.stringify({ type: "start", target: mode });
}

function setMode(next) {
  mode = next;
  directionLabel.textContent = MODES[mode];
  if (lead) {
    lead.textContent = LEADS[mode];
  }
  directionMenu.querySelectorAll("button").forEach((button) => {
    button.setAttribute("aria-checked", button.dataset.mode === mode ? "true" : "false");
  });
  directionMenu.hidden = true;
  directionToggle.setAttribute("aria-expanded", "false");
  if (socket && socket.readyState === WebSocket.OPEN) {
    live = blank();
    render();
    socket.send(startMessage());
  }
}

directionToggle.addEventListener("click", () => {
  const open = directionMenu.hidden;
  directionMenu.hidden = !open;
  directionToggle.setAttribute("aria-expanded", open ? "true" : "false");
});

directionMenu.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) {
    return;
  }
  setMode(button.dataset.mode);
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".direction")) {
    directionMenu.hidden = true;
    directionToggle.setAttribute("aria-expanded", "false");
  }
});

function blank() {
  return { source: "", translation: "" };
}

function shellBridge() {
  const host = globalThis.harmonyShell;
  if (!host || typeof host.start !== "function" || typeof host.stop !== "function") {
    return null;
  }
  return host;
}

function decodePcm(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

globalThis.onHarmonyPcm = (b64) => {
  if (!b64 || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  socket.send(decodePcm(b64));
};

globalThis.onHarmonyMicDenied = () => {
  if (socket) {
    socket.close();
    socket = null;
  }
  show("mic");
};

function stopShell() {
  const bridge = shellBridge();
  if (bridge) {
    bridge.stop();
  }
}

function show(name) {
  for (const [key, panel] of Object.entries(panels)) {
    panel.hidden = key !== name;
  }
  const labels = {
    ready: "准备",
    listening: "正在听",
    mic: "麦克风不可用",
    down: "连接中断",
    history: "历史",
  };
  status.textContent = labels[name];
}

const SPEAKER_SVG = `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M4 9v6h4l5 4V5L8 9H4zm11.5 3a3.5 3.5 0 0 0-1.8-3.06v6.12A3.5 3.5 0 0 0 15.5 12zM14 4.23v2.06a6 6 0 0 1 0 11.42v2.06a8 8 0 0 0 0-15.54z"/></svg>`;

let playContext = null;
let activeSource = null;
let playToken = 0;
let activeText = "";
let activeState = "";
const wavCache = new Map();

function playContextOrNew() {
  if (!playContext) {
    playContext = new AudioContext();
  }
  return playContext;
}

function stopSpeaking() {
  if (activeSource) {
    activeSource.onended = null;
    try {
      activeSource.stop();
    } catch {
      // already stopped
    }
    activeSource = null;
  }
  activeText = "";
  activeState = "";
}

function haltSpeaking() {
  playToken += 1;
  stopSpeaking();
  paintSpeakButtons();
}

window.stopSpeaking = haltSpeaking;

function paintSpeakButtons() {
  document.querySelectorAll("button.speak").forEach((button) => {
    const text = button.dataset.speak || "";
    button.classList.remove("error");
    button.classList.toggle("playing", activeState === "playing" && text === activeText);
    button.classList.toggle("busy", activeState === "busy" && text === activeText);
  });
}

function speakButton(text, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "speak";
  button.dataset.speak = text;
  button.setAttribute("aria-label", label);
  button.innerHTML = SPEAKER_SVG;
  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleSpeak(text);
  });
  return button;
}

async function toggleSpeak(text) {
  const context = playContextOrNew();
  const resume = context.resume();
  if (activeText === text && (activeState === "playing" || activeState === "busy")) {
    playToken += 1;
    stopSpeaking();
    paintSpeakButtons();
    return;
  }
  const token = playToken + 1;
  playToken = token;
  stopSpeaking();
  activeText = text;
  activeState = "busy";
  paintSpeakButtons();
  try {
    await resume;
    let buffer = wavCache.get(text);
    if (!buffer) {
      const response = await fetch(`/tts?text=${encodeURIComponent(text)}`);
      if (!response.ok) {
        throw new Error("tts");
      }
      const bytes = await response.arrayBuffer();
      buffer = await context.decodeAudioData(bytes.slice(0));
      if (wavCache.size >= 20) {
        const oldest = wavCache.keys().next().value;
        wavCache.delete(oldest);
      }
      wavCache.set(text, buffer);
    }
    if (token !== playToken) {
      return;
    }
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    source.onended = () => {
      if (activeSource !== source) {
        return;
      }
      activeSource = null;
      activeText = "";
      activeState = "";
      paintSpeakButtons();
    };
    activeSource = source;
    activeState = "playing";
    source.start();
    paintSpeakButtons();
  } catch {
    if (token !== playToken) {
      return;
    }
    stopSpeaking();
    paintSpeakButtons();
    document.querySelectorAll("button.speak").forEach((button) => {
      if (button.dataset.speak === text) {
        button.classList.add("error");
      }
    });
  }
}

function appendSpoken(row, text, label, sourceLine) {
  const line = document.createElement("p");
  line.className = "line";
  const words = document.createElement(sourceLine ? "strong" : "span");
  words.textContent = text || (sourceLine ? "…" : "");
  line.append(words);
  const spoken = text.trim();
  if (spoken) {
    const button = speakButton(spoken, label);
    if (activeState === "playing" && spoken === activeText) {
      button.classList.add("playing");
    }
    if (activeState === "busy" && spoken === activeText) {
      button.classList.add("busy");
    }
    line.append(button);
  }
  row.append(line);
}

function renderHistoryRow(row, item) {
  if (item.kind === "failed") {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = "这句失败";
    row.append(tag);
  } else if (item.kind === "partial") {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = "未完成";
    row.append(tag);
  }
  appendSpoken(row, item.source || "", "播放原文", true);
  if (item.translation) {
    appendSpoken(row, item.translation, "播放译文", false);
  } else if (item.note) {
    const note = document.createElement("span");
    note.textContent = item.note;
    row.append(note);
  }
}

window.renderHistoryRow = renderHistoryRow;

function renderHistory(list, items) {
  list.replaceChildren();
  for (const item of items) {
    const row = document.createElement("li");
    row.className = item.kind;
    renderHistoryRow(row, item);
    list.append(row);
  }
  list.scrollTop = 0;
}

function render() {
  liveSource.textContent = live.source;
  liveTranslation.textContent = live.translation;
  renderHistory(historyList, history);
  renderHistory(downHistory, history);
}

function lineText(line) {
  if (!line || typeof line !== "object") {
    return false;
  }
  return Boolean((line.source || "").trim() || (line.translation || "").trim() || (line.note || "").trim());
}

function normalizeLine(line) {
  const kind = line.kind === "failed" || line.kind === "partial" ? line.kind : "ok";
  const normalized = {
    source: line.source || "",
    translation: line.translation || "",
    kind,
  };
  if (line.note) {
    normalized.note = line.note;
  }
  return normalized;
}

function collectLines(items, current) {
  const lines = [];
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (lineText(item)) {
      lines.push(normalizeLine(item));
    }
  }
  if (current && lineText(current)) {
    lines.push(normalizeLine({ ...current, kind: "partial" }));
  }
  return lines;
}

function loadSessions() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((item) => item && typeof item === "object" && Array.isArray(item.lines))
      .slice(0, SESSION_LIMIT);
  } catch {
    return [];
  }
}

function formatWhen(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function saveSessionLines(lines, direction) {
  const clean = (Array.isArray(lines) ? lines : []).filter(lineText).map(normalizeLine);
  if (!clean.length) {
    return "empty";
  }
  const sessions = loadSessions();
  sessions.unshift({
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    time: new Date().toISOString(),
    direction: (direction || MODES[mode] || "").trim(),
    lines: clean,
  });
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.slice(0, SESSION_LIMIT)));
  return "saved";
}

globalThis.univoiceSaveSession = saveSessionLines;

function visiblePanel() {
  for (const name of ["ready", "listening", "mic", "down"]) {
    if (panels[name] && !panels[name].hidden) {
      return name;
    }
  }
  return historyReturn || "ready";
}

function renderSessionList() {
  const sessions = loadSessions();
  sessionList.replaceChildren();
  historyEmpty.hidden = sessions.length > 0;
  for (const session of sessions) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "session-row";
    const when = document.createElement("span");
    when.className = "session-when";
    when.textContent = formatWhen(session.time);
    const direction = document.createElement("span");
    direction.className = "session-direction";
    direction.textContent = session.direction || "";
    const preview = document.createElement("span");
    preview.className = "session-preview";
    const first = (session.lines || []).find(lineText);
    preview.textContent = first ? first.source || first.translation || first.note || "" : "";
    button.append(when, direction, preview);
    button.addEventListener("click", () => openSession(session.id));
    item.append(button);
    sessionList.append(item);
  }
}

function openSession(id) {
  const session = loadSessions().find((item) => item.id === id);
  if (!session) {
    openSessionId = null;
    sessionDetail.hidden = true;
    sessionListWrap.hidden = false;
    renderSessionList();
    return;
  }
  openSessionId = id;
  const when = formatWhen(session.time);
  const direction = session.direction || "";
  sessionMeta.textContent = direction ? `${when} · ${direction}` : when;
  renderHistory(sessionLines, session.lines || []);
  sessionListWrap.hidden = true;
  sessionDetail.hidden = false;
}

function openHistory() {
  if (panels.history.hidden) {
    historyReturn = visiblePanel();
  }
  openSessionId = null;
  sessionDetail.hidden = true;
  sessionListWrap.hidden = false;
  directionMenu.hidden = true;
  directionToggle.setAttribute("aria-expanded", "false");
  renderSessionList();
  show("history");
}

function closeHistory() {
  if (openSessionId) {
    openSessionId = null;
    sessionDetail.hidden = true;
    sessionListWrap.hidden = false;
    renderSessionList();
    return;
  }
  show(historyReturn || "ready");
}

async function stopTransport() {
  stopping = true;
  stopShell();
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "stop" }));
  }
  if (socket) {
    socket.close();
    socket = null;
  }
  await releaseAudio();
}

let savingSession = false;

async function newSession() {
  if (savingSession) {
    return;
  }
  haltSpeaking();
  savingSession = true;
  try {
    const active = Boolean(socket || mediaStream || audioContext || workletNode);
    if (active) {
      await stopTransport();
    }
    const lines = collectLines(history, live);
    let result = "empty";
    try {
      result = saveSessionLines(lines);
    } catch {
      result = "error";
    }
    if (result === "error") {
      readyError.hidden = false;
      readyError.textContent = "这次没能保存到本机";
      show("ready");
      return;
    }
    readyError.hidden = true;
    history = [];
    live = blank();
    render();
    show("ready");
  } finally {
    savingSession = false;
  }
}

function pushHistory(kind, note) {
  if (!live.source && !live.translation && kind === "ok") {
    return;
  }
  history.unshift({
    source: live.source,
    translation: live.translation,
    kind,
    note,
  });
  live = blank();
  render();
}

function onCaption(event) {
  if (event.type === "source") {
    live.source = event.text;
  } else {
    live.translation = event.text;
  }
  render();
  if (event.type === "translation" && event.final) {
    pushHistory("ok");
  }
}

async function releaseAudio() {
  if (workletNode) {
    workletNode.disconnect();
    workletNode = null;
  }
  if (audioContext) {
    await audioContext.close();
    audioContext = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  if (wakeLock) {
    await wakeLock.release().catch(() => {});
    wakeLock = null;
  }
}

async function userStop() {
  haltSpeaking();
  stopping = true;
  stopShell();
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "stop" }));
    socket.close();
  }
  socket = null;
  await releaseAudio();
  live = blank();
  render();
  show("ready");
}

function onSocketClose() {
  if (stopping) {
    return;
  }
  if (live.source || live.translation) {
    pushHistory("partial");
  }
  socket = null;
  stopShell();
  releaseAudio();
  show("down");
}

async function startAudio(stream) {
  audioContext = new AudioContext();
  await audioContext.audioWorklet.addModule("/audio-worklet.js");
  const source = audioContext.createMediaStreamSource(stream);
  workletNode = new AudioWorkletNode(audioContext, "downsample-16k");
  workletNode.port.onmessage = (event) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(event.data);
    }
  };
  source.connect(workletNode);
  await audioContext.resume();
}

async function requestWakeLock() {
  if (!navigator.wakeLock) {
    return;
  }
  try {
    wakeLock = await navigator.wakeLock.request("screen");
  } catch {
    wakeLock = null;
  }
}

function openSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${protocol}//${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  return new Promise((resolve, reject) => {
    ws.addEventListener("open", () => resolve(ws), { once: true });
    ws.addEventListener("error", () => reject(new Error("connect")), { once: true });
  });
}

function attachSocket(ws) {
  ws.addEventListener("message", (event) => {
    if (stopping || socket !== ws) {
      return;
    }
    const payload = JSON.parse(event.data);
    if (payload.type === "source" || payload.type === "translation") {
      onCaption(payload);
      return;
    }
    if (payload.type !== "error") {
      return;
    }
    if (payload.code === "auth" || payload.message === "连不上服务器") {
      readyError.hidden = false;
      readyError.textContent = payload.message;
      userStop();
      return;
    }
    if (payload.message === "连接中断") {
      if (live.source || live.translation) {
        pushHistory("partial");
      }
      stopping = true;
      stopShell();
      if (socket) {
        socket.close();
        socket = null;
      }
      releaseAudio();
      show("down");
      return;
    }
    pushHistory("failed", payload.message);
  });
  ws.addEventListener("close", onSocketClose);
}

async function startFromShell() {
  stopping = false;
  readyError.hidden = true;
  let ws;
  try {
    ws = await openSocket();
  } catch {
    readyError.hidden = false;
    readyError.textContent = "连不上服务器";
    show("ready");
    return;
  }
  socket = ws;
  attachSocket(ws);
  ws.send(startMessage());
  shellBridge().start();
  if (stopping || !socket || socket.readyState !== WebSocket.OPEN) {
    stopShell();
    return;
  }
  show("listening");
}

async function start() {
  if (shellBridge()) {
    return startFromShell();
  }
  stopping = false;
  readyError.hidden = true;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      video: false,
    });
  } catch {
    show("mic");
    return;
  }
  mediaStream = stream;
  let ws;
  try {
    ws = await openSocket();
  } catch {
    await releaseAudio();
    readyError.hidden = false;
    readyError.textContent = "连不上服务器";
    show("ready");
    return;
  }
  socket = ws;
  attachSocket(ws);
  ws.send(startMessage());
  await startAudio(stream);
  if (stopping || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  await requestWakeLock();
  show("listening");
}

document.querySelector("#start").addEventListener("click", start);
document.querySelector("#retry-mic").addEventListener("click", start);
document.querySelector("#reconnect").addEventListener("click", start);
document.querySelector("#stop").addEventListener("click", userStop);
document.querySelectorAll(".new-session").forEach((button) => {
  button.addEventListener("click", newSession);
});
document.querySelector("#history-open").addEventListener("click", openHistory);
document.querySelector("#history-back").addEventListener("click", closeHistory);

document.addEventListener("visibilitychange", () => {
  if (shellBridge()) {
    return;
  }
  if (document.visibilityState === "hidden" && socket) {
    userStop();
  }
});

show("ready");
