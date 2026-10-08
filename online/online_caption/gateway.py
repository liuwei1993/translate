"""浏览器会话：方向切换、音频帧、模型事件。不直接连网。"""

import base64

from online_caption.model_map import CaptionMapper, session_update


class GatewaySession:
    def __init__(self) -> None:
        self._mapper = CaptionMapper()
        self._open = False

    @property
    def mapper(self) -> CaptionMapper:
        return self._mapper

    def start(self, target: str) -> list[dict]:
        update = session_update(target)
        outgoing: list[dict] = []
        if self._open:
            outgoing.append({"type": "session.finish"})
            self._mapper.reset()
        outgoing.append(update)
        self._open = True
        return outgoing

    def audio(self, pcm: bytes) -> list[dict]:
        return [
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm).decode("ascii"),
            }
        ]

    def stop(self) -> list[dict]:
        if not self._open:
            return []
        self._open = False
        self._mapper.reset()
        return [{"type": "session.finish"}]

    def ingest(self, event: dict) -> list[dict]:
        return self._mapper.feed(event)

    def disconnect(self) -> list[dict]:
        was_open = self._open
        self._open = False
        self._mapper.reset()
        if not was_open:
            return []
        return [{"type": "error", "code": "upstream", "message": "连接中断"}]
