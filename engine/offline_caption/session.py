from offline_caption.types import Direction


class CaptionSession:
    def __init__(self, asr, translators: dict, direction: Direction):
        self.asr = asr
        self.translators = translators
        self.direction = direction
        self._last_source = ""

    def set_direction(self, direction: Direction) -> None:
        self.direction = direction
        self.asr.reset()
        self._last_source = ""

    def feed(self, samples: list[float], now: float) -> list[dict]:
        del now
        event = self.asr.accept(samples)
        if event is None:
            return []
        text = event.text.strip()
        if not text:
            return []
        if not event.final and text == self._last_source:
            return []
        self._last_source = text
        caption = {
            "source": text,
            "translation": self.translators[self.direction].translate(text),
            "final": event.final,
        }
        if event.final:
            self.asr.reset()
            self._last_source = ""
        return [caption]
