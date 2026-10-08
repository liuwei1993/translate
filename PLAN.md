# 断网字幕流水线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前仓库做出一条断网可运行的中英同声字幕流水线：wav 进去，原文和译文的 JSON 行出来。

**Architecture:** `CaptionSession` 只认两个接口：流式识别吐出增量文本，翻译器把一句原文译成一句译文。句末静音后该行冻结。桌面用 sherpa-onnx 和 Opus-MT 的 ONNX 实现这两个接口。鸿蒙壳不在本计划里，见 `OUTLINE.md`。

**Tech Stack:** Python 3.10+、pytest、sherpa-onnx、numpy、optimum ONNX Runtime、transformers。

---

## 文件

- Create: `engine/pyproject.toml`
- Create: `engine/offline_caption/__init__.py`
- Create: `engine/offline_caption/types.py`
- Create: `engine/offline_caption/asr.py`
- Create: `engine/offline_caption/translate.py`
- Create: `engine/offline_caption/session.py`
- Create: `engine/offline_caption/wav.py`
- Create: `engine/offline_caption/cli.py`
- Create: `engine/tests/test_session.py`
- Create: `engine/tests/test_sherpa_asr.py`
- Create: `engine/tests/test_marian.py`
- Create: `scripts/download_models.sh`
- Modify: `.gitignore`（已有，执行时确认仍忽略 `models/`）

模型下载到 `models/`，不提交。

### Task 1: 会话类型和假实现

**Files:**
- Create: `engine/pyproject.toml`
- Create: `engine/offline_caption/__init__.py`
- Create: `engine/offline_caption/types.py`
- Create: `engine/offline_caption/asr.py`
- Create: `engine/offline_caption/translate.py`
- Create: `engine/offline_caption/session.py`
- Test: `engine/tests/test_session.py`

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/test_session.py
from offline_caption.asr import AsrEvent, ScriptedAsr
from offline_caption.session import CaptionSession
from offline_caption.translate import PrefixTranslator
from offline_caption.types import Direction


def test_partial_caption_uses_current_direction():
    session = CaptionSession(
        asr=ScriptedAsr([AsrEvent("这个多少钱", final=False)]),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
    )
    captions = session.feed([0.0], now=1.0)
    assert captions == [
        {"source": "这个多少钱", "translation": "en:这个多少钱", "final": False}
    ]


def test_final_caption_then_next_utterance_starts_clean():
    session = CaptionSession(
        asr=ScriptedAsr(
            [
                AsrEvent("这个多少钱", final=True),
                AsrEvent("二十美元", final=False),
            ]
        ),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
    )
    first = session.feed([0.0], now=1.0)
    second = session.feed([0.0], now=2.0)
    assert first[0]["final"] is True
    assert second[0]["source"] == "二十美元"
    assert second[0]["final"] is False


def test_direction_switch_uses_the_other_translator():
    session = CaptionSession(
        asr=ScriptedAsr(
            [
                AsrEvent("这个多少钱", final=False),
                AsrEvent("how much", final=False),
            ]
        ),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
    )
    session.feed([0.0], now=1.0)
    session.set_direction(Direction.EN_TO_ZH)
    captions = session.feed([0.0], now=2.0)
    assert captions[0]["translation"] == "zh:how much"


def test_empty_asr_event_emits_nothing():
    session = CaptionSession(
        asr=ScriptedAsr([None]),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
    )
    assert session.feed([0.0], now=1.0) == []
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd /home/simon/codes/translate && python -m pytest engine/tests/test_session.py -v`

Expected: FAIL，`offline_caption` 无法导入。

- [ ] **Step 3: 写最小实现**

```toml
# engine/pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "offline-caption"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest"]
asr = ["sherpa-onnx", "numpy"]
mt = ["optimum[onnxruntime]", "transformers", "onnxruntime"]

[tool.setuptools.packages.find]
where = ["."]
include = ["offline_caption*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

pytest 的根目录是 `engine/`，所以后面的命令都在 `engine` 下跑。

```python
# engine/offline_caption/__init__.py
"""Offline bilingual caption pipeline."""
```

```python
# engine/offline_caption/types.py
from enum import Enum


class Direction(Enum):
    ZH_TO_EN = "zh2en"
    EN_TO_ZH = "en2zh"
```

```python
# engine/offline_caption/asr.py
from dataclasses import dataclass


@dataclass(frozen=True)
class AsrEvent:
    text: str
    final: bool


class ScriptedAsr:
    def __init__(self, events: list[AsrEvent | None]):
        self._events = list(events)

    def accept(self, samples: list[float]) -> AsrEvent | None:
        del samples
        if not self._events:
            return None
        return self._events.pop(0)

    def reset(self) -> None:
        return None
```

```python
# engine/offline_caption/translate.py
class PrefixTranslator:
    def __init__(self, prefix: str):
        self.prefix = prefix

    def translate(self, text: str) -> str:
        return f"{self.prefix}:{text}"
```

```python
# engine/offline_caption/session.py
from offline_caption.types import Direction


class CaptionSession:
    def __init__(self, asr, translators: dict, direction: Direction):
        self.asr = asr
        self.translators = translators
        self.direction = direction
        self._last_source = ""

    def set_direction(self, direction: Direction) -> None:
        self.direction = direction
        self.asr.reset()
        self._last_source = ""

    def feed(self, samples: list[float], now: float) -> list[dict]:
        del now
        event = self.asr.accept(samples)
        if event is None:
            return []
        text = event.text.strip()
        if not text:
            return []
        if not event.final and text == self._last_source:
            return []
        self._last_source = text
        caption = {
            "source": text,
            "translation": self.translators[self.direction].translate(text),
            "final": event.final,
        }
        if event.final:
            self.asr.reset()
            self._last_source = ""
        return [caption]
```

- [ ] **Step 4: 安装 pytest 并确认通过**

Run: `cd /home/simon/codes/translate/engine && python -m pip install -e ".[dev]" && python -m pytest tests/test_session.py -v`

Expected: 4 passed.

- [ ] **Step 5: 初始化 git 并提交**

```bash
cd /home/simon/codes/translate
git init
git add .gitignore OUTLINE.md PLAN.md engine
git commit -m "$(cat <<'EOF'
Add the offline caption session and its update rules.

EOF
)"
```

### Task 2: 句内防抖

**Files:**
- Modify: `engine/tests/test_session.py`
- Modify: `engine/offline_caption/session.py`

- [ ] **Step 1: 追加失败测试**

在 `engine/tests/test_session.py` 末尾追加：

```python
def test_partial_updates_inside_the_interval_are_dropped():
    session = CaptionSession(
        asr=ScriptedAsr(
            [
                AsrEvent("这个", final=False),
                AsrEvent("这个多少", final=False),
            ]
        ),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
        min_interval_s=0.3,
    )
    first = session.feed([0.0], now=1.0)
    second = session.feed([0.0], now=1.1)
    assert first[0]["source"] == "这个"
    assert second == []


def test_final_is_emitted_even_inside_the_interval():
    session = CaptionSession(
        asr=ScriptedAsr(
            [
                AsrEvent("这个", final=False),
                AsrEvent("这个多少钱", final=True),
            ]
        ),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
        min_interval_s=0.3,
    )
    session.feed([0.0], now=1.0)
    captions = session.feed([0.0], now=1.1)
    assert captions[0]["source"] == "这个多少钱"
    assert captions[0]["final"] is True
```

- [ ] **Step 2: 跑测试，确认新测试失败**

Run: `cd /home/simon/codes/translate/engine && python -m pytest tests/test_session.py::test_partial_updates_inside_the_interval_are_dropped -v`

Expected: FAIL，`CaptionSession.__init__` 不接受 `min_interval_s`。

- [ ] **Step 3: 加上 300 ms 间隔**

把 `engine/offline_caption/session.py` 换成：

```python
from offline_caption.types import Direction


class CaptionSession:
    def __init__(self, asr, translators: dict, direction: Direction, min_interval_s: float = 0.3):
        self.asr = asr
        self.translators = translators
        self.direction = direction
        self.min_interval_s = min_interval_s
        self._last_source = ""
        self._last_at = -1_000.0

    def set_direction(self, direction: Direction) -> None:
        self.direction = direction
        self.asr.reset()
        self._last_source = ""
        self._last_at = -1_000.0

    def feed(self, samples: list[float], now: float) -> list[dict]:
        event = self.asr.accept(samples)
        if event is None:
            return []
        text = event.text.strip()
        if not text:
            return []
        if not event.final and text == self._last_source:
            return []
        if not event.final and (now - self._last_at) < self.min_interval_s:
            return []
        self._last_source = text
        self._last_at = now
        caption = {
            "source": text,
            "translation": self.translators[self.direction].translate(text),
            "final": event.final,
        }
        if event.final:
            self.asr.reset()
            self._last_source = ""
            self._last_at = -1_000.0
        return [caption]
```

- [ ] **Step 4: 跑全部会话测试**

Run: `cd /home/simon/codes/translate/engine && python -m pytest tests/test_session.py -v`

Expected: 6 passed。

- [ ] **Step 5: 提交**

```bash
cd /home/simon/codes/translate
git add engine/tests/test_session.py engine/offline_caption/session.py
git commit -m "$(cat <<'EOF'
Keep partial caption updates from firing on every audio frame.

EOF
)"
```

### Task 3: 流式识别适配

**Files:**
- Create: `engine/offline_caption/wav.py`
- Modify: `engine/offline_caption/asr.py`
- Create: `engine/tests/test_sherpa_asr.py`
- Create: `scripts/download_models.sh`

- [ ] **Step 1: 写 wav 读取测试和识别适配测试**

```python
# engine/tests/test_sherpa_asr.py
import wave
from pathlib import Path

import pytest

from offline_caption.asr import SherpaStreamingAsr
from offline_caption.wav import read_wave

MODEL = Path(__file__).resolve().parents[2] / "models" / "asr"
WAV = MODEL / "test_wavs" / "1.wav"


def test_read_wave_normalizes_int16(tmp_path: Path):
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes((b"\x00\x40" * 160))
    samples, sample_rate = read_wave(str(path))
    assert sample_rate == 16000
    assert samples.shape == (160,)
    assert samples.dtype.name == "float32"
    assert abs(float(samples[0]) - (0x4000 / 32768)) < 1e-6


@pytest.mark.skipif(not WAV.is_file(), reason="ASR model wav is not downloaded")
def test_sherpa_emits_text_and_a_final_after_silence():
    asr = SherpaStreamingAsr(
        tokens=str(MODEL / "tokens.txt"),
        encoder=str(MODEL / "encoder-epoch-99-avg-1.int8.onnx"),
        decoder=str(MODEL / "decoder-epoch-99-avg-1.onnx"),
        joiner=str(MODEL / "joiner-epoch-99-avg-1.int8.onnx"),
    )
    samples, sample_rate = read_wave(str(WAV))
    assert sample_rate == 16000
    texts = []
    finals = []
    hop = 1600
    for start in range(0, len(samples), hop):
        event = asr.accept(samples[start : start + hop])
        if event and event.text:
            texts.append(event.text)
            finals.append(event.final)
    silence = [0.0] * 16000
    event = asr.accept(silence)
    if event and event.text:
        texts.append(event.text)
        finals.append(event.final)
    assert texts
    assert any(finals)
```

- [ ] **Step 2: 跑测试，确认 wav 测试失败**

Run: `cd /home/simon/codes/translate/engine && python -m pytest tests/test_sherpa_asr.py::test_read_wave_normalizes_int16 -v`

Expected: FAIL，`offline_caption.wav` 无法导入。带模型的测试在模型下载前会被 skip。

- [ ] **Step 3: 实现 wav 读取和 sherpa 适配**

```python
# engine/offline_caption/wav.py
import wave

import numpy as np


def read_wave(path: str):
    with wave.open(path) as handle:
        if handle.getnchannels() != 1:
            raise ValueError("wav must be mono")
        if handle.getsampwidth() != 2:
            raise ValueError("wav must be 16-bit")
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768
    return samples, sample_rate
```

在 `engine/offline_caption/asr.py` 末尾追加：

```python
class SherpaStreamingAsr:
    def __init__(self, tokens: str, encoder: str, decoder: str, joiner: str, num_threads: int = 2):
        import sherpa_onnx

        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=tokens,
            encoder=encoder,
            decoder=decoder,
            joiner=joiner,
            num_threads=num_threads,
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
            provider="cpu",
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=0.8,
            rule3_min_utterance_length=20,
        )
        self._stream = self._recognizer.create_stream()

    def accept(self, samples) -> AsrEvent | None:
        import numpy as np

        array = np.asarray(samples, dtype=np.float32)
        self._stream.accept_waveform(16000, array)
        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)
        raw = self._recognizer.get_result(self._stream)
        text = (raw if isinstance(raw, str) else raw.text).strip()
        final = self._recognizer.is_endpoint(self._stream)
        if not text and not final:
            return None
        return AsrEvent(text=text, final=final)

    def reset(self) -> None:
        self._recognizer.reset(self._stream)
```

```bash
# scripts/download_models.sh
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASR_DIR="$ROOT/models/asr"
if [[ -f "$ASR_DIR/tokens.txt" ]]; then
  echo "ASR model already present"
  exit 0
fi
mkdir -p "$ROOT/models"
TMP="$(mktemp -d)"
curl -L -o "$TMP/asr.tar.bz2" \
  https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2
tar -xjf "$TMP/asr.tar.bz2" -C "$TMP"
rm -rf "$ASR_DIR"
mv "$TMP"/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20 "$ASR_DIR"
rm -rf "$TMP"
test -f "$ASR_DIR/encoder-epoch-99-avg-1.int8.onnx"
test -f "$ASR_DIR/decoder-epoch-99-avg-1.onnx"
test -f "$ASR_DIR/joiner-epoch-99-avg-1.int8.onnx"
test -f "$ASR_DIR/tokens.txt"
```

- [ ] **Step 4: 跑不依赖模型的测试**

Run: `cd /home/simon/codes/translate/engine && python -m pip install -e ".[dev,asr]" && python -m pytest tests/test_sherpa_asr.py::test_read_wave_normalizes_int16 tests/test_session.py -v`

Expected: PASS。`test_sherpa_emits_text_and_a_final_after_silence` 在执行下载脚本之前 skip。

- [ ] **Step 5: 下载模型并跑识别测试**

```bash
chmod +x /home/simon/codes/translate/scripts/download_models.sh
/home/simon/codes/translate/scripts/download_models.sh
cd /home/simon/codes/translate/engine && python -m pytest tests/test_sherpa_asr.py -v
```

Expected: 2 passed。压缩包大约 488 MB，解压后的 int8 编码器是 174 MB。

- [ ] **Step 6: 提交代码，不提交模型**

```bash
cd /home/simon/codes/translate
git check-ignore -v models/asr/tokens.txt
git add engine/offline_caption/asr.py engine/offline_caption/wav.py engine/tests/test_sherpa_asr.py scripts/download_models.sh
git commit -m "$(cat <<'EOF'
Decode mic-rate audio with the bilingual streaming recognizer.

EOF
)"
```

Expected: `git check-ignore` 打印 `.gitignore:2:models/ models/asr/tokens.txt`。

### Task 4: Opus-MT 翻译器

**Files:**
- Modify: `engine/offline_caption/translate.py`
- Create: `engine/tests/test_marian.py`
- Modify: `scripts/download_models.sh`

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/test_marian.py
from pathlib import Path

import pytest

from offline_caption.translate import MarianOnnxTranslator

ZH_EN = Path(__file__).resolve().parents[2] / "models" / "mt" / "zh-en"


@pytest.mark.skipif(not (ZH_EN / "encoder_model.onnx").is_file(), reason="MT model is not exported")
def test_marian_translates_a_short_chinese_sentence():
    translator = MarianOnnxTranslator(str(ZH_EN))
    text = translator.translate("这个多少钱")
    assert text
    assert text != "这个多少钱"
    lowered = text.lower()
    assert "how much" in lowered or "price" in lowered or "cost" in lowered


EN_ZH = Path(__file__).resolve().parents[2] / "models" / "mt" / "en-zh"


@pytest.mark.skipif(not (EN_ZH / "encoder_model.onnx").is_file(), reason="MT model is not exported")
def test_marian_translates_a_short_english_sentence():
    translator = MarianOnnxTranslator(str(EN_ZH))
    text = translator.translate("How much is this?")
    assert text
    assert "多少" in text or "钱" in text
```

- [ ] **Step 2: 跑测试，确认在模型缺失时 skip，在类缺失时失败**

Run: `cd /home/simon/codes/translate/engine && python -m pytest tests/test_marian.py -v`

Expected: 收集测试时 FAIL，因为 `MarianOnnxTranslator` 还不存在。先把类的空壳放上再测 skip 不符合本步。本步预期是 ImportError 或 AttributeError。

- [ ] **Step 3: 实现翻译器并扩展下载脚本**

在 `engine/offline_caption/translate.py` 末尾追加：

```python
class MarianOnnxTranslator:
    def __init__(self, model_dir: str):
        from optimum.onnxruntime import ORTModelForSeq2SeqLM
        from transformers import MarianTokenizer

        self._tokenizer = MarianTokenizer.from_pretrained(model_dir)
        self._model = ORTModelForSeq2SeqLM.from_pretrained(model_dir)

    def translate(self, text: str) -> str:
        batch = self._tokenizer(text, return_tensors="pt")
        output = self._model.generate(**batch, max_new_tokens=64)
        return self._tokenizer.decode(output[0], skip_special_tokens=True).strip()
```

把下面这段加到 `scripts/download_models.sh` 的末尾：

```bash
export_mt() {
  local repo="$1"
  local dest="$2"
  if [[ -f "$dest/encoder_model.onnx" ]]; then
    echo "MT model already present: $dest"
    return
  fi
  mkdir -p "$dest"
  python -m pip install "optimum[onnxruntime]" transformers onnxruntime
  optimum-cli export onnx --model "$repo" --task translation "$dest"
  test -f "$dest/encoder_model.onnx"
}

export_mt Helsinki-NLP/opus-mt-zh-en "$ROOT/models/mt/zh-en"
export_mt Helsinki-NLP/opus-mt-en-zh "$ROOT/models/mt/en-zh"
```

- [ ] **Step 4: 导出模型并跑测试**

```bash
/home/simon/codes/translate/scripts/download_models.sh
cd /home/simon/codes/translate/engine && python -m pip install -e ".[dev,mt]" && python -m pytest tests/test_marian.py -v
```

Expected: 2 passed。中文「这个多少钱」的译文里能看到 how much、price 或 cost。英文 “How much is this?” 的译文里能看到「多少」或「钱」。optimum 导出后目录里应有 `encoder_model.onnx`。

- [ ] **Step 5: 提交**

```bash
cd /home/simon/codes/translate
git add engine/offline_caption/translate.py engine/tests/test_marian.py scripts/download_models.sh
git commit -m "$(cat <<'EOF'
Translate committed source text with on-disk Opus-MT models.

EOF
)"
```

### Task 5: 命令行

**Files:**
- Create: `engine/offline_caption/cli.py`
- Create: `engine/tests/test_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/test_cli.py
import json

from offline_caption.cli import format_caption


def test_format_caption_is_one_json_object():
    line = format_caption({"source": "这个多少钱", "translation": "How much is this?", "final": True})
    assert json.loads(line) == {
        "source": "这个多少钱",
        "translation": "How much is this?",
        "final": True,
    }
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd /home/simon/codes/translate/engine && python -m pytest tests/test_cli.py -v`

Expected: FAIL，`offline_caption.cli` 无法导入。

- [ ] **Step 3: 实现命令行**

```python
# engine/offline_caption/cli.py
import argparse
import json
from pathlib import Path

from offline_caption.asr import SherpaStreamingAsr
from offline_caption.session import CaptionSession
from offline_caption.translate import MarianOnnxTranslator
from offline_caption.types import Direction
from offline_caption.wav import read_wave


def format_caption(caption: dict) -> str:
    return json.dumps(caption, ensure_ascii=False)


def build_session(model_root: Path, direction: Direction) -> CaptionSession:
    asr_dir = model_root / "asr"
    asr = SherpaStreamingAsr(
        tokens=str(asr_dir / "tokens.txt"),
        encoder=str(asr_dir / "encoder-epoch-99-avg-1.int8.onnx"),
        decoder=str(asr_dir / "decoder-epoch-99-avg-1.onnx"),
        joiner=str(asr_dir / "joiner-epoch-99-avg-1.int8.onnx"),
    )
    translators = {
        Direction.ZH_TO_EN: MarianOnnxTranslator(str(model_root / "mt" / "zh-en")),
        Direction.EN_TO_ZH: MarianOnnxTranslator(str(model_root / "mt" / "en-zh")),
    }
    return CaptionSession(asr=asr, translators=translators, direction=direction)


def captions_for_wav(session: CaptionSession, path: str) -> list[dict]:
    samples, sample_rate = read_wave(path)
    if sample_rate != 16000:
        raise ValueError("wav must be 16000 Hz")
    emitted = []
    now = 0.0
    hop = 1600
    chunks = [samples[start : start + hop] for start in range(0, len(samples), hop)]
    chunks.append([0.0] * 16000)
    for chunk in chunks:
        now += len(chunk) / 16000
        emitted.extend(session.feed(chunk.tolist() if hasattr(chunk, "tolist") else chunk, now))
    return emitted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", required=True)
    parser.add_argument("--direction", choices=["zh2en", "en2zh"], default="zh2en")
    parser.add_argument("--models", default=str(Path(__file__).resolve().parents[2] / "models"))
    args = parser.parse_args()
    direction = Direction.ZH_TO_EN if args.direction == "zh2en" else Direction.EN_TO_ZH
    session = build_session(Path(args.models), direction)
    for caption in captions_for_wav(session, args.wav):
        print(format_caption(caption))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试，并对示例 wav 打出字幕**

```bash
cd /home/simon/codes/translate/engine && python -m pytest tests/test_cli.py tests/test_session.py -v
python -m offline_caption.cli --wav /home/simon/codes/translate/models/asr/test_wavs/1.wav --direction zh2en
```

Expected: pytest PASS。命令在断网时仍打印若干行 JSON，其中至少一行 `"final": true`。

- [ ] **Step 5: 提交**

```bash
cd /home/simon/codes/translate
git add engine/offline_caption/cli.py engine/tests/test_cli.py
git commit -m "$(cat <<'EOF'
Print streaming captions for a wav file without using the network.

EOF
)"
```

## 本计划不包含的下一步

鸿蒙工程 `apps/pura70` 等这条命令对 `models/asr/test_wavs/1.wav` 打出带 `final: true` 的英文译文后再写。壳的行为以 `engine/tests/test_session.py` 为准：300 ms 内的句内增量丢掉，句末冻结，切换方向后使用另一个翻译器。
