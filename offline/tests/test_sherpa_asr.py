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
