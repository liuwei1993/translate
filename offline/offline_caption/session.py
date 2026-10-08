from offline_caption.types import Direction


class CaptionSession:
    def __init__(self, asr, translators: dict, direction: Direction, min_interval_s: float = 0.3):
        self.asr = asr
        self.translators = translators
        self.direction = direction
        self.min_interval_s = min_interval_s
        self._last_source = ""
        self._last_at = -1_000.0

    def set_direction(self, direction: Direction) -> None:
        self.direction = direction
        self.asr.reset()
        self._last_source = ""
        self._last_at = -1_000.0

    def feed(self, samples: list[float], now: float) -> list[dict]:
        event = self.asr.accept(samples)
        if event is None:
            return []
        text = event.text.strip()
        if not text:
            return []
        if not event.final and text == self._last_source:
            return []
        if not event.final and (now - self._last_at) < self.min_interval_s:
            return []
        self._last_source = text
        self._last_at = now
        caption = {
            "source": text,
            "translation": self.translators[self.direction].translate(text),
            "final": event.final,
        }
        if event.final:
            self.asr.reset()
            self._last_source = ""
            self._last_at = -1_000.0
        return [caption]
