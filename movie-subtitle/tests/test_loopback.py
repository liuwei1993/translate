import numpy as np

from movie_caption.audio import PcmFramer
from movie_caption.loopback import pull_pcm


def test_fake_loopback_becomes_one_pcm_frame():
    def reader(frames: int):
        assert frames == 4800
        return np.full((frames, 2), 0.5, dtype=np.float32)

    frames = pull_pcm(reader, 4800, 48000, PcmFramer())
    assert len(frames) == 1
    assert len(frames[0]) == 3200
    assert np.frombuffer(frames[0], dtype="<i2")[0] == 16383
