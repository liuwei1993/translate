const status = document.querySelector("#status");
const panels = {
  ready: document.querySelector("#panel-ready"),
  listening: document.querySelector("#panel-listening"),
  mic: document.querySelector("#panel-mic"),
  down: document.querySelector("#panel-down"),
};
const readyError = document.querySelector("#ready-error");
const liveSource = document.querySelector("#live-source");
const liveTranslation = document.querySelector("#live-translation");
const historyList = document.querySelector("#history");
const downHistory = document.querySelector("#down-history");

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
};
const LEADS = {
  auto: "说中文就出英文，说英文就出中文。",
  en: "只把中文译成英文。",
  zh: "只把英文译成中文。",
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
  };
  status.textContent = labels[name];
}

function renderHistory(list, items) {
  list.replaceChildren();
  for (const item of items) {
    const row = document.createElement("li");
    row.className = item.kind;
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
    const source = document.createElement("strong");
    source.textContent = item.source || "…";
    const translation = document.createElement("span");
    translation.textContent = item.translation || item.note || "";
    row.append(source, translation);
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

document.addEventListener("visibilitychange", () => {
  if (shellBridge()) {
    return;
  }
  if (document.visibilityState === "hidden" && socket) {
    userStop();
  }
});

show("ready");
