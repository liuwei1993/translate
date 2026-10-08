"""根据原文是中文还是英文，决定采用哪一路译文。"""


def speech_language(text: str) -> str | None:
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin = sum(1 for char in text if char.isascii() and char.isalpha())
    if cjk == 0 and latin == 0:
        return None
    if cjk > 0 and latin == 0:
        return "zh"
    if latin > 0 and cjk == 0:
        return "en"
    return "zh" if cjk >= latin else "en"


class CaptionRouter:
    """两路译文里，只把和原文相对的那一路交给页面。"""

    def __init__(self) -> None:
        self.target: str | None = None
        self._held: dict[str, list[dict]] = {"en": [], "zh": []}

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
            previous = self.target
            self._apply(event.get("text") or "")
            released = self._take_held()
            if previous is not None and self.target != previous:
                return [{"type": "translation", "text": "", "final": False}, event, *released]
            return [event, *released]
        if kind != "translation":
            return []
        if self.target is None:
            self._held.setdefault(lane, []).append(event)
            return []
        if lane != self.target:
            return []
        if event.get("final"):
            self.target = None
            self._held = {"en": [], "zh": []}
        return [event]

    def _apply(self, text: str) -> None:
        detected = speech_language(text)
        if detected is None:
            return
        self.target = "en" if detected == "zh" else "zh"
        other = "zh" if self.target == "en" else "en"
        self._held[other] = []

    def _take_held(self) -> list[dict]:
        if self.target is None:
            return []
        held = self._held.get(self.target, [])
        self._held[self.target] = []
        if any(item.get("final") for item in held):
            self.target = None
            self._held = {"en": [], "zh": []}
        return held
