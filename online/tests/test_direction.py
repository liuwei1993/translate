from online_caption.direction import CaptionRouter, speech_language


def test_speech_language_distinguishes_chinese_and_english():
    assert speech_language("你好") == "zh"
    assert speech_language("It's twenty") == "en"
    assert speech_language("20") is None


def test_chinese_speech_uses_the_english_translation():
    router = CaptionRouter()
    assert router.feed("en", [{"type": "translation", "text": "Hello", "final": False}]) == []
    assert router.feed("zh", [{"type": "translation", "text": "你好", "final": False}]) == []
    shown = router.feed("en", [{"type": "source", "text": "你好", "final": False}])
    assert shown == [
        {"type": "source", "text": "你好", "final": False},
        {"type": "translation", "text": "Hello", "final": False},
    ]
    assert router.feed("en", [{"type": "translation", "text": "Hello.", "final": False}]) == [
        {"type": "translation", "text": "Hello.", "final": False}
    ]
    assert router.feed("zh", [{"type": "translation", "text": "忽略", "final": False}]) == []


def test_english_speech_uses_the_chinese_translation():
    router = CaptionRouter()
    router.feed("zh", [{"type": "translation", "text": "二十美元", "final": False}])
    shown = router.feed("en", [{"type": "source", "text": "It's twenty", "final": False}])
    assert {"type": "translation", "text": "二十美元", "final": False} in shown


def test_next_sentence_can_switch_direction():
    router = CaptionRouter()
    router.feed("en", [{"type": "source", "text": "你好", "final": False}])
    assert router.feed("en", [{"type": "translation", "text": "Hello", "final": True}]) == [
        {"type": "translation", "text": "Hello", "final": True}
    ]
    router.feed("zh", [{"type": "translation", "text": "二十", "final": False}])
    shown = router.feed("en", [{"type": "source", "text": "twenty", "final": False}])
    assert {"type": "source", "text": "twenty", "final": False} in shown
    assert {"type": "translation", "text": "二十", "final": False} in shown
