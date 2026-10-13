import wave
from pathlib import Path

import numpy as np

from movie_caption.audio import PcmFramer, read_wav


def test_sixteen_khz_mono_fills_one_frame():
    frames = PcmFramer().feed(np.full(1600, 0.5, dtype=np.float32), 16000)
    assert len(frames) == 1
    assert len(frames[0]) == 3200
    assert np.frombuffer(frames[0], dtype="<i2")[0] == 16383


def test_short_audio_waits_until_a_frame_is_full():
    framer = PcmFramer()
    assert framer.feed(np.full(800, 0.5, dtype=np.float32), 16000) == []
    frames = framer.feed(np.full(800, 0.5, dtype=np.float32), 16000)
    assert len(frames) == 1
    assert len(frames[0]) == 3200


def test_flush_emits_the_tail():
    framer = PcmFramer()
    assert framer.feed(np.full(100, 0.25, dtype=np.float32), 16000) == []
    tail = framer.flush()
    assert len(tail) == 1
    assert len(tail[0]) == 200


def test_wav_reader_downmixes_stereo(tmp_path: Path):
    path = tmp_path / "stereo.wav"
    pcm = np.array([32767, 0], dtype="<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(pcm.tobytes())
    samples, rate = read_wav(str(path))
    assert rate == 16000
    assert samples.shape == (1, 2)
    framer = PcmFramer()
    assert framer.feed(samples, rate) == []
    heard = np.frombuffer(framer.flush()[0], dtype="<i2")
    assert heard.tolist() == [16383]
