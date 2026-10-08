# 断网同声字幕 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在华为 Pura 70（HarmonyOS 7）上做出一个断网可用的同声字幕应用：麦克风听一路语音，屏幕同时滚出原文和中英译文。

**Architecture:** 界面只依赖一个字幕引擎。引擎在手机本地把麦克风音频送给流式识别，识别出的原文按句提交给端侧文本翻译，再把原文和译文交给界面。识别和翻译都在独立线程，不走网络。

**Tech Stack:** HarmonyOS 7 ArkTS、AudioCapturer、sherpa-onnx 1.13.x（流式 Zipformer）、ONNX 文本翻译模型、Hypium（纯逻辑单测）。验收机是 ADY-AL10，12 GB，麒麟 9010E。

---

## 大纲

第一版只做这件事：手机离线听对方说话，屏幕上原文一行、译文一行，说完一句译文跟上。

```
麦克风
  → 字幕引擎
       → 流式识别（中英 Zipformer，常驻）
       → 文本翻译（当前方向的一个模型，常驻）
  → 字幕页
```

已定的边界：

- 设备只认 Pura 70，系统是 HarmonyOS 7。安装包是 HAP，不是安卓 APK，也不是网页。
- 断网后仍能开始一场字幕。模型在开发阶段用 `hdc file send` 放进手机，运行时不再下载。
- 同一时刻只听一种语言。屏幕上一个开关在「英语 → 中文」和「中文 → 英语」之间切换。第一版不做自动判断语种。
- 只出文字，不朗读。
- 语种只做中文和英文。
- 应用停在前台，屏幕保持常亮。切到后台就停止录音。

明确不做：账号、历史记录、语种商店、云端兜底、语音合成、两人同时说话、高通 NPU。鸿蒙公开文档里没有可靠的系统离线翻译 API，不调用 `@ohos.ai.translate` 或 `textTranslation`。

## 两条被放弃的做法

端到端语音翻译（音频直接变成另一种语言的文字）模型太大，原文和译文绑在一起，字幕不好对照。按整段调用 Whisper 再翻译，在手机上不是流式，跟不上说话。所以用「流式识别 + 按句翻译」。

## 运行时行为

识别的中间结果马上显示为原文。译文不跟着每一个字刷新。

满足任一条才翻译当前原文：

- 识别端点判定这句话说完了
- 原文相对上次翻译新增至少 12 个字符，并且距离上次翻译已经超过 600 毫秒

说完的一句进滚动列表，最多保留 8 句。正在说的一句单独显示在底部，字号更大。

## 模型

识别用 sherpa-onnx 的中英流式 Zipformer，2023-02-20 这版：

- `encoder-epoch-99-avg-1.int8.onnx`（174 MB）
- `decoder-epoch-99-avg-1.onnx`（14 MB）
- `joiner-epoch-99-avg-1.int8.onnx`（3.1 MB）
- `tokens.txt`

识别线程数固定为 2。

翻译用 Helsinki-NLP 的两个方向，运行时只加载当前方向：

- 英语 → 中文：`opus-mt-en-zh`
- 中文 → 英语：`opus-mt-zh-en`

每个方向大约 560 MB（float 的 encoder + decoder）。12 GB 内存同时驻留识别模型加一个翻译方向是够的。两个方向不要同时加载。

## 文件

```
docs/superpowers/plans/2026-10-08-offline-subtitle.md
app/                                          HarmonyOS 工程
  AppScope/app.json5
  oh-package.json5                            依赖 sherpa_onnx
  entry/src/main/module.json5                 麦克风权限
  entry/src/main/ets/pages/SubtitlePage.ets   只画字幕和开关
  entry/src/main/ets/engine/SubtitleEngine.ets
  entry/src/main/ets/engine/translatePolicy.ts
  entry/src/main/ets/engine/translatePolicy.test.ets
  entry/src/main/ets/audio/MicCapturer.ets
  entry/src/main/ets/workers/StreamingAsrWorker.ets
  entry/src/main/ets/mt/OpusTranslator.ets
  entry/src/main/resources/rawfile/            不提交 onnx 大文件
models/README.md                              模型来源和 hdc 推送命令
.gitignore
```

界面、录音、识别、翻译各自一个文件。纯策略 `translatePolicy.ts` 不引用鸿蒙 API，才能在没有真机时单测。

## 引擎接口

界面和测试只依赖这个形状：

```ts
type Direction = 'en-zh' | 'zh-en'

interface SubtitleEvent {
  liveSource: string
  liveTranslation: string
  lines: Array<{ source: string; translation: string }>
}

interface SubtitleEngine {
  start(direction: Direction): Promise<void>
  stop(): Promise<void>
  setDirection(direction: Direction): Promise<void>
  onChange(cb: (event: SubtitleEvent) => void): void
}
```

`setDirection` 先停当前识别流，换成另一个翻译模型，再开始新的一句。不保留切换前的半句。

---

### Task 1: 仓库骨架和模型说明

**Files:**

- Create: `.gitignore`
- Create: `models/README.md`
- Create: `app/oh-package.json5`
- Create: `app/AppScope/app.json5`
- Create: `app/entry/src/main/module.json5`

- [ ] **Step 1: 忽略大文件和本地会话**

`.gitignore`：

```gitignore
.superpowers/
models/**/*.onnx
models/**/*.bin
app/entry/src/main/resources/rawfile/**
!app/entry/src/main/resources/rawfile/.gitkeep
```

- [ ] **Step 2: 写下模型怎么放进手机**

`models/README.md` 写明两个下载来源，以及推到设备的命令：

```bash
hdc file send models/asr /data/local/tmp/translate-asr
hdc file send models/mt /data/local/tmp/translate-mt
```

应用首次启动时如果沙箱里没有这些文件，从 `/data/local/tmp` 拷进应用文件目录。拷贝失败时字幕页显示「模型未安装」，不崩溃，也不访问网络。

- [ ] **Step 3: 声明包名和麦克风**

`app/oh-package.json5`：

```json5
{
  "modelVersion": "5.0.0",
  "name": "offline-subtitle",
  "version": "1.0.0",
  "dependencies": {
    "sherpa_onnx": "1.13.4"
  }
}
```

`app/entry/src/main/module.json5` 的 `requestPermissions` 只有一项：`name` 为 `ohos.permission.MICROPHONE`，`reason` 为「把听到的话转成字幕」，`usedScene.when` 为 `inuse`。

- [ ] **Step 4: Commit**

```bash
git add .gitignore models/README.md app/oh-package.json5 app/AppScope/app.json5 app/entry/src/main/module.json5
git commit -m "chore: scaffold offline HarmonyOS subtitle app"
```

### Task 2: 翻译时机的纯逻辑

**Files:**

- Create: `app/entry/src/main/ets/engine/translatePolicy.ts`
- Test: `app/entry/src/main/ets/engine/translatePolicy.test.ets`

- [ ] **Step 1: 写失败测试**

```ts
import { decideTranslation } from './translatePolicy'

test('partial source does not translate until it grows and waits', () => {
  const first = decideTranslation({
    source: 'hello',
    isFinal: false,
    lastTranslatedSource: '',
    nowMs: 1000,
    lastTranslateMs: 0
  })
  expect(first.translate).eq(false)

  const tooSoon = decideTranslation({
    source: 'hello there friend',
    isFinal: false,
    lastTranslatedSource: 'hello',
    nowMs: 1400,
    lastTranslateMs: 1000
  })
  expect(tooSoon.translate).eq(false)

  const ready = decideTranslation({
    source: 'hello there friend',
    isFinal: false,
    lastTranslatedSource: 'hello',
    nowMs: 1700,
    lastTranslateMs: 1000
  })
  expect(ready.translate).eq(true)
  expect(ready.source).eq('hello there friend')
})

test('endpoint always translates the utterance', () => {
  const decision = decideTranslation({
    source: 'thanks',
    isFinal: true,
    lastTranslatedSource: '',
    nowMs: 1000,
    lastTranslateMs: 999
  })
  expect(decision.translate).eq(true)
})

test('blank source never translates', () => {
  const decision = decideTranslation({
    source: '   ',
    isFinal: true,
    lastTranslatedSource: '',
    nowMs: 1000,
    lastTranslateMs: 0
  })
  expect(decision.translate).eq(false)
})
```

- [ ] **Step 2: 跑测试，确认失败**

在 DevEco 里对 `translatePolicy.test.ets` 跑 Hypium。预期：找不到 `decideTranslation`。

- [ ] **Step 3: 实现策略**

```ts
export interface TranslateInput {
  source: string
  isFinal: boolean
  lastTranslatedSource: string
  nowMs: number
  lastTranslateMs: number
}

export interface TranslateDecision {
  translate: boolean
  source: string
}

const MIN_GROWTH = 12
const MIN_GAP_MS = 600

export function decideTranslation(input: TranslateInput): TranslateDecision {
  const source = input.source.trim()
  if (source.length === 0) {
    return { translate: false, source: '' }
  }
  if (input.isFinal) {
    return { translate: true, source }
  }
  const grew = source.length - input.lastTranslatedSource.trim().length
  const waited = input.nowMs - input.lastTranslateMs
  if (grew >= MIN_GROWTH && waited >= MIN_GAP_MS) {
    return { translate: true, source }
  }
  return { translate: false, source }
}
```

- [ ] **Step 4: 再跑测试，确认通过**

- [ ] **Step 5: Commit**

```bash
git add app/entry/src/main/ets/engine/translatePolicy.ts app/entry/src/main/ets/engine/translatePolicy.test.ets
git commit -m "feat: decide when a partial utterance is ready to translate"
```

### Task 3: 用假引擎把字幕页做出来

**Files:**

- Create: `app/entry/src/main/ets/pages/SubtitlePage.ets`
- Create: `app/entry/src/main/ets/engine/FakeSubtitleEngine.ets`

- [ ] **Step 1: 假引擎按时间发出两句**

`FakeSubtitleEngine.start` 后每 400 毫秒把原文变长，满 600 毫秒更新一次译文，两句之后停止。不打开麦克风。

- [ ] **Step 2: 字幕页**

深色全屏。顶部一个按钮，文案是当前方向，点按调用 `setDirection`。中部列出已完成的句子，每句原文在上、译文在下。底部大字显示 `liveSource` 和 `liveTranslation`。右下角「开始 / 停止」。

- [ ] **Step 3: 在 Pura 70 上看假数据**

`hdc install` 后打开应用。预期：不申请麦克风也能看到字往外长；点方向开关，按钮文案在「英语 → 中文」和「中文 → 英语」之间变化。

- [ ] **Step 4: Commit**

```bash
git add app/entry/src/main/ets/pages/SubtitlePage.ets app/entry/src/main/ets/engine/FakeSubtitleEngine.ets
git commit -m "feat: show streaming subtitles with a fake engine"
```

### Task 4: 麦克风

**Files:**

- Create: `app/entry/src/main/ets/audio/MicCapturer.ets`
- Modify: `app/entry/src/main/ets/pages/SubtitlePage.ets`

- [ ] **Step 1: 采集 16 kHz、单声道、S16LE**

用 `audio.createAudioCapturer`。`SOURCE_TYPE_MIC`。每帧转成 `Float32Array`，样本除以 32768。回调把样本交给引擎，不在回调里做识别。

- [ ] **Step 2: 权限被拒绝时停在说明页**

拒绝后不重试循环。页面写「需要麦克风才能出字幕」，并给一个再次请求的按钮。

- [ ] **Step 3: 保持屏幕常亮，离开页面就停**

`window.setWindowKeepScreenOn(true)` 在 `start` 时打开，`stop` 和页面销毁时关掉，并 `mic.release()`。

- [ ] **Step 4: 真机确认有输入**

开始后页面显示最近 1 秒的音量峰值。对着手机说话，数值上升；静音时接近 0。此时还没有文字。

- [ ] **Step 5: Commit**

```bash
git add app/entry/src/main/ets/audio/MicCapturer.ets app/entry/src/main/ets/pages/SubtitlePage.ets
git commit -m "feat: capture microphone audio on device"
```

### Task 5: 流式识别，先只出原文

**Files:**

- Create: `app/entry/src/main/ets/workers/StreamingAsrWorker.ets`
- Create: `app/entry/src/main/ets/engine/SubtitleEngine.ets`
- Modify: `app/entry/src/main/ets/pages/SubtitlePage.ets`

- [ ] **Step 1: Worker 加载 Zipformer**

按 sherpa-onnx HarmonyOS 示例创建 `OnlineRecognizer`。`numThreads = 2`，`enableEndpoint = true`。模型从应用文件目录读，不从网络拉。加载失败把错误字符串回给界面。

- [ ] **Step 2: 音频进流，文本出来**

主线程把 `Float32Array` 发给 worker。worker 调用 `acceptWaveform`、`decode`，把 `{ text, isEndpoint }` 发回。端点之后 `reset` 流，开始下一句。

- [ ] **Step 3: 界面接上真识别**

`SubtitlePage` 改为使用 `SubtitleEngine`，不再使用 `FakeSubtitleEngine`。这一步 `liveTranslation` 先等于空字符串。原文应在说话过程中变长。

- [ ] **Step 4: 飞行模式下验收识别**

打开飞行模式，开始字幕，说一句英语和一句普通话。预期：两句都能出原文，应用没有网络请求。说完约 1 秒内句子落到滚动列表。

- [ ] **Step 5: Commit**

```bash
git add app/entry/src/main/ets/workers/StreamingAsrWorker.ets app/entry/src/main/ets/engine/SubtitleEngine.ets
git commit -m "feat: stream on-device bilingual speech recognition"
```

### Task 6: 端侧翻译接到句尾

**Files:**

- Create: `app/entry/src/main/ets/mt/OpusTranslator.ets`
- Modify: `app/entry/src/main/ets/engine/SubtitleEngine.ets`

- [ ] **Step 1: 一个方向一个翻译器**

`OpusTranslator.load(direction)` 只加载对应的 encoder、decoder 和 sentencepiece。`translate(source)` 返回整句译文。切换方向时释放上一个模型再加载新的。

- [ ] **Step 2: 引擎调用 decideTranslation**

worker 每来一次识别结果，用 Task 2 的函数决定要不要翻译。要翻译时在翻译线程跑 `OpusTranslator`，回来后更新 `liveTranslation`。端点结果追加进 `lines`，并清空 live 两行。列表超过 8 句时丢掉最旧的一句。

- [ ] **Step 3: 飞行模式验收整条链路**

飞行模式。方向「英语 → 中文」，说 “How much is this?”。预期：原文先出现，一句结束后出现中文译文。再点切换，说「这个多少钱」，出现英文译文。全程无需网络。

- [ ] **Step 4: 连续说两分钟**

连续说话约两分钟。预期：字幕继续跟，应用不被系统杀掉，译文不在每个音节上跳动。若发热后原文明显落后说话超过 2 秒，把识别线程从 2 降到 1 再测一次，并把结果写进 `models/README.md`。

- [ ] **Step 5: Commit**

```bash
git add app/entry/src/main/ets/mt/OpusTranslator.ets app/entry/src/main/ets/engine/SubtitleEngine.ets models/README.md
git commit -m "feat: translate recognized speech offline on device"
```

## 完成标准

在 Pura 70 上打开飞行模式，不插 SIM、不连 Wi-Fi：

1. 能开始和停止字幕。
2. 英语说完，屏幕上有英文原文和中文译文。
3. 切换后中文说完，屏幕上有中文原文和英文译文。
4. 中间结果只稳定地改原文；译文按句或按 600 毫秒以上的增量更新。
5. 离开页面后麦克风释放，屏幕恢复自动熄灭。

## 自检

- 飞行模式验收覆盖断网。
- 方向开关覆盖两种语言。
- 原文和译文分成识别、翻译两段，界面不直接碰模型。
- 没有把系统翻译 API、云端、语音合成写进任务。
- `decideTranslation` 的阈值 12 字和 600 毫秒只在 `translatePolicy.ts` 里定义，Task 6 调用它，不另写一套。
