"""根据原文语种，决定采用哪一路译文。"""

PAIRS = {
    "auto": ("en", "zh"),
    "en": ("en", "zh"),
    "zh": ("en", "zh"),
    "ja-auto": ("zh", "ja"),
    "ja": ("zh", "ja"),
    "ja2zh": ("zh", "ja"),
}

# 单向模式要求的原文语种。互译不限制，只要原文落在当前语言对里。
REQUIRED_SOURCE = {
    "auto": None,
    "en": "zh",
    "zh": "en",
    "ja-auto": None,
    "ja": "zh",
    "ja2zh": "ja",
}


def lanes_for(mode: str) -> tuple[str, str]:
    try:
        return PAIRS[mode]
    except KeyError:
        raise ValueError(mode) from None


def speech_language(text: str, languages: tuple[str, ...] = ("en", "zh")) -> str | None:
    kana = sum(1 for char in text if "\u3040" <= char <= "\u30ff")
    han = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin = sum(1 for char in text if char.isascii() and char.isalpha())
    if "ja" in languages and kana > 0:
        return "ja"
    if "zh" in languages and han > 0:
        return "zh"
    if "en" in languages and latin > 0:
        return "en"
    return None


class CaptionRouter:
    """只把和原文不同语种的译文交给页面。"""

    def __init__(self, mode: str = "auto") -> None:
        self.mode = "auto"
        self._lanes: tuple[str, ...] = ()
        self._source_lane = "en"
        self._source_text = ""
        self._source_lang: str | None = None
        self._latest: dict[str, dict | None] = {}
        self._emitted: tuple[str, bool] | None = None
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        lanes = lanes_for(mode)
        if lanes != self._lanes:
            self._lanes = lanes
            self._latest = {name: None for name in lanes}
            self._source_text = ""
            self._source_lang = None
            self._emitted = None
        self.mode = mode
        self._source_lane = "en" if "en" in lanes else "zh"

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
            if lane != self._source_lane:
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
            self._source_lang = speech_language(text, self._lanes)
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
        if self._source_lang not in self._lanes:
            return self._clear()
        required = REQUIRED_SOURCE[self.mode]
        if required is not None and self._source_lang != required:
            return self._clear()
        want = next(name for name in self._lanes if name != self._source_lang)
        item = self._latest.get(want)
        if not item or not (item.get("text") or "").strip():
            return self._clear()
        if speech_language(item["text"], self._lanes) != want:
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
