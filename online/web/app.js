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

let target = "en";
let socket = null;
let mediaStream = null;
let audioContext = null;
let workletNode = null;
let wakeLock = null;
let stopping = false;
let live = blank();
let history = [];

function blank() {
  return { source: "", translation: "" };
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

function selectedButtons() {
  document.querySelectorAll(".choice").forEach((button) => {
    button.classList.toggle("selected", button.dataset.target === target);
  });
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
  list.scrollTop = list.scrollHeight;
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
  history.push({
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

async function start() {
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
  ws.send(JSON.stringify({ type: "start", target }));
  await startAudio(stream);
  if (stopping || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  await requestWakeLock();
  show("listening");
  selectedButtons();
}

document.querySelector("#ready-choices").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) {
    return;
  }
  target = button.dataset.target;
  selectedButtons();
});

document.querySelector("#panel-listening .direction-row").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button || button.dataset.target === target || !socket) {
    return;
  }
  target = button.dataset.target;
  selectedButtons();
  live = blank();
  render();
  socket.send(JSON.stringify({ type: "start", target }));
});

document.querySelector("#start").addEventListener("click", start);
document.querySelector("#retry-mic").addEventListener("click", start);
document.querySelector("#reconnect").addEventListener("click", start);
document.querySelector("#stop").addEventListener("click", userStop);

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && socket) {
    userStop();
  }
});

selectedButtons();
show("ready");
