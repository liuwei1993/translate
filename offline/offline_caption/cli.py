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
