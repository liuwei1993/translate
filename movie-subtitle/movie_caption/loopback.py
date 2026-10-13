"""默认扬声器回环。Linux 走 Pulse，Windows 走 WASAPI，都由 soundcard 打开。"""

from movie_caption.audio import PcmFramer


def pull_pcm(reader, frames: int, sample_rate: int, framer: PcmFramer) -> list[bytes]:
    return framer.feed(reader(frames), sample_rate)


def default_loopback():
    import soundcard as sc

    speaker = sc.default_speaker()
    if speaker is None:
        raise RuntimeError("没有默认扬声器")
    name = str(speaker.name)
    matches = [
        mic
        for mic in sc.all_microphones(include_loopback=True)
        if mic.isloopback and (mic.name == name or name in mic.name)
    ]
    if not matches:
        raise RuntimeError("没有默认扬声器")
    exact = [mic for mic in matches if mic.name == name]
    return exact[0] if exact else matches[0]


def open_default_loopback(sample_rate: int):
    context = default_loopback().recorder(samplerate=sample_rate, blocksize=sample_rate // 10)
    return context.__enter__(), context


def capture_into(pcm_queue, on_event, stop, sample_rate: int = 48000) -> None:
    framer = PcmFramer()
    try:
        recorder, context = open_default_loopback(sample_rate)
    except Exception:
        on_event({"type": "error", "code": "upstream", "message": "没有回环设备"})
        return
    frames = sample_rate // 10
    try:
        while not stop.is_set():
            for chunk in pull_pcm(recorder.record, frames, sample_rate, framer):
                pcm_queue.put(chunk)
    except Exception:
        on_event({"type": "error", "code": "upstream", "message": "没有回环设备"})
    finally:
        context.__exit__(None, None, None)
