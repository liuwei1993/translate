"""收成网页网关要求的 16 kHz 单声道 16 bit PCM。"""

import wave

import numpy as np

CHUNK_BYTES = 3200


def to_mono(samples: np.ndarray) -> np.ndarray:
    array = np.asarray(samples, dtype=np.float32)
    if array.ndim == 1:
        return array
    return array.mean(axis=1)


def resample(samples: np.ndarray, source_rate: int, target_rate: int = 16000) -> np.ndarray:
    if len(samples) == 0 or source_rate == target_rate:
        return samples
    target_len = int(round(len(samples) * target_rate / source_rate))
    if target_len <= 0:
        return np.zeros(0, dtype=np.float32)
    position = np.linspace(0, len(samples) - 1, target_len)
    left = np.floor(position).astype(np.int64)
    right = np.minimum(left + 1, len(samples) - 1)
    weight = (position - left).astype(np.float32)
    return samples[left] * (1 - weight) + samples[right] * weight


def float_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


class PcmFramer:
    def __init__(self) -> None:
        self._pending = b""

    def feed(self, samples: np.ndarray, sample_rate: int) -> list[bytes]:
        self._pending += float_to_pcm16(resample(to_mono(samples), sample_rate))
        frames = []
        while len(self._pending) >= CHUNK_BYTES:
            frames.append(self._pending[:CHUNK_BYTES])
            self._pending = self._pending[CHUNK_BYTES:]
        return frames

    def flush(self) -> list[bytes]:
        if not self._pending:
            return []
        frame = self._pending
        self._pending = b""
        return [frame]


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path) as handle:
        if handle.getsampwidth() != 2:
            raise ValueError("wav must be 16-bit")
        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768
    if channels > 1:
        samples = samples.reshape(-1, channels)
    return samples, sample_rate


def feed_wav(path: str, pcm_queue, stop) -> None:
    import time

    samples, sample_rate = read_wav(path)
    framer = PcmFramer()
    chunks = framer.feed(samples, sample_rate)
    chunks.extend(framer.flush())
    for chunk in chunks:
        if stop.is_set():
            return
        pcm_queue.put(chunk)
        time.sleep(len(chunk) / 32000)
