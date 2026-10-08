"""把 qwen3.8-livetranslate 的服务端事件收成网页字幕事件。"""


def session_update(target: str) -> dict:
    if target not in ("en", "zh"):
        raise ValueError(f"不支持的目标语言: {target}")
    return {
        "type": "session.update",
        "session": {
            "output_modalities": ["text"],
            "translation": {"language": target},
        },
    }


class CaptionMapper:
    def __init__(self) -> None:
        self._source = ""
        self._translation = ""

    def reset(self) -> None:
        self._source = ""
        self._translation = ""

    def feed(self, event: dict) -> list[dict]:
        kind = event.get("type")
        if kind == "conversation.item.input_audio_transcription.delta":
            self._source += event.get("delta") or ""
            return [{"type": "source", "text": self._source, "final": False}]
        if kind == "conversation.item.input_audio_transcription.completed":
            text = event.get("transcript") or self._source
            self._source = ""
            return [{"type": "source", "text": text, "final": True}]
        if kind == "response.text.delta":
            self._translation += event.get("delta") or ""
            return [{"type": "translation", "text": self._translation, "final": False}]
        if kind == "response.done":
            text = self._translation
            self._translation = ""
            if text == "":
                return []
            return [{"type": "translation", "text": text, "final": True}]
        if kind == "error":
            message = event.get("message") or "上游错误"
            return [{"type": "error", "code": "upstream", "message": message}]
        return []
