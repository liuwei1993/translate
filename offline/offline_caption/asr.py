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


class SherpaStreamingAsr:
    def __init__(self, tokens: str, encoder: str, decoder: str, joiner: str, num_threads: int = 2):
        import sherpa_onnx

        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=tokens,
            encoder=encoder,
            decoder=decoder,
            joiner=joiner,
            num_threads=num_threads,
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
            provider="cpu",
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=0.4,
            rule3_min_utterance_length=20,
        )
        self._stream = self._recognizer.create_stream()

    def accept(self, samples) -> AsrEvent | None:
        import numpy as np

        array = np.asarray(samples, dtype=np.float32)
        self._stream.accept_waveform(16000, array)
        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)
        raw = self._recognizer.get_result(self._stream)
        text = (raw if isinstance(raw, str) else raw.text).strip()
        final = self._recognizer.is_endpoint(self._stream)
        if not text and not final:
            return None
        return AsrEvent(text=text, final=final)

    def reset(self) -> None:
        self._recognizer.reset(self._stream)
