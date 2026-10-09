"""根据原文是中文还是英文，决定采用哪一路译文。"""


def speech_language(text: str) -> str | None:
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin = sum(1 for char in text if char.isascii() and char.isalpha())
    if cjk > 0:
        return "zh"
    if latin > 0:
        return "en"
    return None


class CaptionRouter:
    """只把和原文不同语种的译文交给页面。英文原文配中文译文，中文原文配英文译文。"""

    def __init__(self, mode: str = "auto") -> None:
        self.mode = "auto"
        self._source_text = ""
        self._source_lang: str | None = None
        self._latest: dict[str, dict | None] = {"en": None, "zh": None}
        self._emitted: tuple[str, bool] | None = None
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        if mode not in ("auto", "en", "zh"):
            raise ValueError(mode)
        self.mode = mode

    def feed(self, lane: str, events: list[dict]) -> list[dict]:
        outgoing: list[dict] = []
        for event in events:
            outgoing.extend(self._one(lane, event))
        return outgoing

    def _one(self, lane: str, event: dict) -> list[dict]:
        kind = event.get("type")
        if kind == "error":
            return [event]
        if kind == "source":
            if lane != "en":
                return []
            text = event.get("text") or ""
            fresh = bool(self._source_text) and not text.startswith(self._source_text)
            had_translation = self._emitted not in (None, ("", False))
            if fresh:
                self._latest = {
                    name: item
                    for name, item in self._latest.items()
                    if item and not item.get("final")
                }
                self._emitted = None
            self._source_text = text
            self._source_lang = speech_language(text)
            picked = self._pick()
            if fresh and had_translation and not picked:
                self._emitted = ("", False)
                return [event, {"type": "translation", "text": "", "final": False}]
            return [event, *picked]
        if kind != "translation":
            return []
        self._latest[lane] = event
        return self._pick()

    def _pick(self) -> list[dict]:
        if self._source_lang is None:
            return []
        if self.mode == "zh" and self._source_lang != "en":
            return self._clear()
        if self.mode == "en" and self._source_lang != "zh":
            return self._clear()
        want = "zh" if self._source_lang == "en" else "en"
        item = self._latest.get(want)
        if not item or not (item.get("text") or "").strip():
            return self._clear()
        if speech_language(item["text"]) != want:
            return self._clear()
        key = (item.get("text") or "", bool(item.get("final")))
        if key == self._emitted:
            return []
        self._emitted = key
        return [item]

    def _clear(self) -> list[dict]:
        if self._emitted in (None, ("", False)):
            return []
        self._emitted = ("", False)
        return [{"type": "translation", "text": "", "final": False}]
