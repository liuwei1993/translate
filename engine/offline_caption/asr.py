from dataclasses import dataclass


@dataclass(frozen=True)
class AsrEvent:
    text: str
    final: bool


class ScriptedAsr:
    def __init__(self, events: list[AsrEvent | None]):
        self._events = list(events)

    def accept(self, samples: list[float]) -> AsrEvent | None:
        del samples
        if not self._events:
            return None
        return self._events.pop(0)

    def reset(self) -> None:
        return None
