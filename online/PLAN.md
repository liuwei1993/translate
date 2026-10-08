# 网页同声字幕 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 手机浏览器打开页面，选「听中文→英文」或「听英文→中文」，对着麦克风说话，屏幕边出原文和译文，一句结束后冻结。

**Architecture:** 网页只认自己的字幕事件。Python 网关把 16 kHz PCM 转成百炼 LiveTranslate 的 WebSocket 事件，再把模型事件收成原文/译文增量。密钥留在仓库根目录的 `.env`，不放进网页。`PLAN.md` 和 `OUTLINE.md` 的断网流水线不动。

**Tech Stack:** Python 3.10+、`websockets`、pytest、静态页面（无框架）、AudioWorklet。本地用 HTTPS，否则安卓 Chrome 不给麦克风。

## 已定行为

- 同一时刻只听一路。方向只有中文→英文、英文→中文，手动切换。
- 只出文字。`session.update` 里 `output_modalities` 为 `["text"]`，不接收、不播放模型音频。
- 原文来自 `conversation.item.input_audio_transcription.delta` / `.completed`。译文来自 `response.text.delta`，`response.done` 冻结这一句。增量只往后接，不改已出现的字。
- 断句用模型默认的 `speaker_detection`（静音约 1 秒）。网页不做静音检测。
- 切换方向或停止：对模型发 `session.finish`，等到 `session.finished` 再关连接。没冻结的当前句丢掉。已冻结历史留在当前页面，刷新即丢。
- 麦克风被拒绝：停在说明页，可再试。网关连不上：停在准备页并写明连不上。听的过程中断开：历史保留，当前句标「未完成」，可重连，重连后从新的一句开始。
- 正在听时请求屏幕常亮；系统不允许时字幕继续。

## 连接

从仓库根目录 `.env` 读取 `LLM_API_KEY`、`LLM_HOST`、`MODEL`。不要读 `LLM_OPEN_AI_URL` 或 `LLM_DASHSCOPE`。

```text
wss://{LLM_HOST}/api-ws/v1/realtime?model={MODEL}
Authorization: Bearer {LLM_API_KEY}
```

密钥若返回 401，页面显示鉴权失败；需要换成同一业务空间里以 `sk-` 开头的按量付费密钥。日志和错误信息里不出现密钥。

## 网页和网关之间的事件

网页发给网关的文本帧：

- `{"type":"start","target":"en"}` 或 `"zh"`
- `{"type":"stop"}`

音频用二进制帧：16 kHz、单声道、16 bit little-endian，约 100 ms 一块（3200 字节）。网页里用 AudioWorklet 把浏览器采样率降到 16 kHz。

网关发给网页的文本帧：

- `{"type":"source","text":"...","final":false}`
- `{"type":"source","text":"...","final":true}`
- `{"type":"translation","text":"...","final":false}`
- `{"type":"translation","text":"...","final":true}`
- `{"type":"error","code":"upstream"|"auth","message":"..."}`

`text` 在 `final:false` 时是这一句到目前为止的全文，不是单个增量碎片。网关负责把模型的 `delta` 拼起来。

## 文件

全部在 `online/`。不修改 `offline/`、仓库根目录的 `PLAN.md`、`OUTLINE.md`。

- `online/pyproject.toml`
- `online/online_caption/model_map.py`
- `online/online_caption/upstream.py`
- `online/online_caption/gateway.py`
- `online/online_caption/server.py`
- `online/web/index.html`、`app.js`、`audio-worklet.js`、`style.css`
- `online/tests/test_model_map.py`
- `online/tests/test_gateway.py`
- `online/tests/test_upstream.py`
