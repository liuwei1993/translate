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
