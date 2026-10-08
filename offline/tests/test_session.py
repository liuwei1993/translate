from offline_caption.asr import AsrEvent, ScriptedAsr
from offline_caption.session import CaptionSession
from offline_caption.translate import PrefixTranslator
from offline_caption.types import Direction


def test_partial_caption_uses_current_direction():
    session = CaptionSession(
        asr=ScriptedAsr([AsrEvent("这个多少钱", final=False)]),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
    )
    captions = session.feed([0.0], now=1.0)
    assert captions == [
        {"source": "这个多少钱", "translation": "en:这个多少钱", "final": False}
    ]


def test_final_caption_then_next_utterance_starts_clean():
    session = CaptionSession(
        asr=ScriptedAsr(
            [
                AsrEvent("这个多少钱", final=True),
                AsrEvent("二十美元", final=False),
            ]
        ),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
    )
    first = session.feed([0.0], now=1.0)
    second = session.feed([0.0], now=2.0)
    assert first[0]["final"] is True
    assert second[0]["source"] == "二十美元"
    assert second[0]["final"] is False


def test_direction_switch_uses_the_other_translator():
    session = CaptionSession(
        asr=ScriptedAsr(
            [
                AsrEvent("这个多少钱", final=False),
                AsrEvent("how much", final=False),
            ]
        ),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
    )
    session.feed([0.0], now=1.0)
    session.set_direction(Direction.EN_TO_ZH)
    captions = session.feed([0.0], now=2.0)
    assert captions[0]["translation"] == "zh:how much"


def test_empty_asr_event_emits_nothing():
    session = CaptionSession(
        asr=ScriptedAsr([None]),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
    )
    assert session.feed([0.0], now=1.0) == []


def test_partial_updates_inside_the_interval_are_dropped():
    session = CaptionSession(
        asr=ScriptedAsr(
            [
                AsrEvent("这个", final=False),
                AsrEvent("这个多少", final=False),
            ]
        ),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
        min_interval_s=0.3,
    )
    first = session.feed([0.0], now=1.0)
    second = session.feed([0.0], now=1.1)
    assert first[0]["source"] == "这个"
    assert second == []


def test_final_is_emitted_even_inside_the_interval():
    session = CaptionSession(
        asr=ScriptedAsr(
            [
                AsrEvent("这个", final=False),
                AsrEvent("这个多少钱", final=True),
            ]
        ),
        translators={
            Direction.ZH_TO_EN: PrefixTranslator("en"),
            Direction.EN_TO_ZH: PrefixTranslator("zh"),
        },
        direction=Direction.ZH_TO_EN,
        min_interval_s=0.3,
    )
    session.feed([0.0], now=1.0)
    captions = session.feed([0.0], now=1.1)
    assert captions[0]["source"] == "这个多少钱"
    assert captions[0]["final"] is True
