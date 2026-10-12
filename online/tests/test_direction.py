from online_caption.direction import CaptionRouter, lanes_for, speech_language


def test_speech_language_distinguishes_chinese_and_english():
    assert speech_language("你好") == "zh"
    assert speech_language("It's twenty") == "en"
    assert speech_language("20") is None
    assert speech_language("東京です") == "zh"


def test_speech_language_treats_kana_as_japanese_on_the_japanese_pair():
    assert speech_language("こんにちは", ("zh", "ja")) == "ja"
    assert speech_language("東京駅に行きます", ("zh", "ja")) == "ja"
    assert speech_language("你好", ("zh", "ja")) == "zh"
    assert speech_language("了解", ("zh", "ja")) == "zh"
    assert speech_language("It's twenty", ("zh", "ja")) is None
    assert speech_language("迈克尔・乔丹", ("zh", "ja")) == "zh"
    assert speech_language("迈克尔·乔丹", ("zh", "ja")) == "zh"
    assert speech_language("ｻﾝﾌﾟﾙ", ("zh", "ja")) == "ja"


def test_lanes_follow_the_selected_pair():
    assert lanes_for("auto") == ("en", "zh")
    assert lanes_for("en") == ("en", "zh")
    assert lanes_for("zh") == ("en", "zh")
    assert lanes_for("ja-auto") == ("zh", "ja")
    assert lanes_for("ja") == ("zh", "ja")
    assert lanes_for("ja2zh") == ("zh", "ja")


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


def test_english_echo_is_not_used_as_the_translation():
    router = CaptionRouter()
    router.feed("en", [{"type": "source", "text": "Hello, how are you?", "final": False}])
    assert router.feed(
        "en",
        [{"type": "translation", "text": "Hello, how are you?", "final": False}],
    ) == []
    assert router.feed(
        "zh",
        [{"type": "translation", "text": "你好。你还好吗？", "final": False}],
    ) == [{"type": "translation", "text": "你好。你还好吗？", "final": False}]
    early = CaptionRouter()
    early.feed("en", [{"type": "translation", "text": "Hello, how are you?", "final": False}])
    shown = early.feed("en", [{"type": "source", "text": "Hello, how are you?", "final": False}])
    assert shown == [{"type": "source", "text": "Hello, how are you?", "final": False}]


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


def test_new_utterance_clears_the_previous_translation():
    router = CaptionRouter()
    router.feed("en", [{"type": "source", "text": "你好", "final": False}])
    router.feed("en", [{"type": "translation", "text": "Hello", "final": False}])
    shown = router.feed("en", [{"type": "source", "text": "how are you", "final": False}])
    assert {"type": "translation", "text": "", "final": False} in shown


def test_chinese_target_ignores_chinese_speech():
    router = CaptionRouter("zh")
    router.feed("en", [{"type": "source", "text": "你好", "final": False}])
    assert router.feed("en", [{"type": "translation", "text": "Hello", "final": False}]) == []
    router.feed("en", [{"type": "source", "text": "how are you", "final": False}])
    assert router.feed("zh", [{"type": "translation", "text": "你好吗？", "final": False}]) == [
        {"type": "translation", "text": "你好吗？", "final": False}
    ]


def test_japanese_pair_ignores_source_from_the_japanese_lane():
    router = CaptionRouter("ja-auto")
    assert router.feed("ja", [{"type": "source", "text": "こんにちは", "final": False}]) == []


def test_chinese_speech_uses_the_japanese_translation():
    router = CaptionRouter("ja-auto")
    shown = router.feed("zh", [{"type": "source", "text": "你好", "final": False}])
    assert shown == [{"type": "source", "text": "你好", "final": False}]
    assert router.feed("ja", [{"type": "translation", "text": "こんにちは", "final": False}]) == [
        {"type": "translation", "text": "こんにちは", "final": False}
    ]
    assert router.feed("zh", [{"type": "translation", "text": "你好呀", "final": False}]) == []


def test_japanese_speech_uses_the_chinese_translation():
    router = CaptionRouter("ja-auto")
    router.feed("zh", [{"type": "translation", "text": "你好", "final": False}])
    shown = router.feed("zh", [{"type": "source", "text": "こんにちは", "final": False}])
    assert {"type": "source", "text": "こんにちは", "final": False} in shown
    assert {"type": "translation", "text": "你好", "final": False} in shown
    assert router.feed("ja", [{"type": "translation", "text": "こんにちは", "final": False}]) == []


def test_kanji_only_japanese_is_treated_as_chinese():
    router = CaptionRouter("ja-auto")
    router.feed("ja", [{"type": "translation", "text": "了解しました", "final": False}])
    shown = router.feed("zh", [{"type": "source", "text": "了解", "final": False}])
    assert {"type": "translation", "text": "了解しました", "final": False} in shown


def test_japanese_target_ignores_japanese_speech():
    router = CaptionRouter("ja")
    router.feed("zh", [{"type": "source", "text": "こんにちは", "final": False}])
    assert router.feed("ja", [{"type": "translation", "text": "你好", "final": False}]) == []
    router.feed("zh", [{"type": "source", "text": "你好", "final": False}])
    assert router.feed("ja", [{"type": "translation", "text": "こんにちは", "final": False}]) == [
        {"type": "translation", "text": "こんにちは", "final": False}
    ]


def test_kanji_only_japanese_translation_is_shown_when_it_is_not_an_echo():
    router = CaptionRouter("ja")
    router.feed("zh", [{"type": "source", "text": "我知道了", "final": False}])
    assert router.feed("ja", [{"type": "translation", "text": "了解", "final": False}]) == [
        {"type": "translation", "text": "了解", "final": False}
    ]
    tokyo = CaptionRouter("ja-auto")
    tokyo.feed("zh", [{"type": "source", "text": "东京", "final": False}])
    assert tokyo.feed("ja", [{"type": "translation", "text": "東京", "final": False}]) == [
        {"type": "translation", "text": "東京", "final": False}
    ]


def test_kanji_only_japanese_echo_is_hidden():
    router = CaptionRouter("ja-auto")
    router.feed("zh", [{"type": "source", "text": "你好", "final": False}])
    assert router.feed("ja", [{"type": "translation", "text": "你好", "final": False}]) == []
    router.feed("zh", [{"type": "source", "text": "我知道了", "final": False}])
    assert router.feed("ja", [{"type": "translation", "text": "了解", "final": False}]) == [
        {"type": "translation", "text": "了解", "final": False}
    ]
    assert router.feed("zh", [{"type": "translation", "text": "了解", "final": False}]) == [
        {"type": "translation", "text": "", "final": False}
    ]


def test_chinese_name_with_katakana_middle_dot_uses_the_japanese_lane():
    router = CaptionRouter("ja-auto")
    router.feed("ja", [{"type": "translation", "text": "マイケル・ジョーダン", "final": False}])
    shown = router.feed("zh", [{"type": "source", "text": "迈克尔・乔丹", "final": False}])
    assert {"type": "source", "text": "迈克尔・乔丹", "final": False} in shown
    assert {"type": "translation", "text": "マイケル・ジョーダン", "final": False} in shown


def test_switching_direction_drops_the_previous_translation():
    router = CaptionRouter("ja-auto")
    router.feed("zh", [{"type": "source", "text": "こんにちは", "final": False}])
    router.feed("zh", [{"type": "translation", "text": "你好呀", "final": False}])
    router.set_mode("ja2zh")
    shown = router.feed("zh", [{"type": "source", "text": "おはよう", "final": False}])
    assert shown == [{"type": "source", "text": "おはよう", "final": False}]


def test_chinese_from_japanese_ignores_chinese_and_kanji_only():
    router = CaptionRouter("ja2zh")
    router.feed("zh", [{"type": "source", "text": "你好", "final": False}])
    assert router.feed("zh", [{"type": "translation", "text": "こんにちは", "final": False}]) == []
    router.feed("zh", [{"type": "source", "text": "了解", "final": False}])
    assert router.feed("zh", [{"type": "translation", "text": "わかりました", "final": False}]) == []
    router.feed("zh", [{"type": "source", "text": "こんにちは", "final": False}])
    assert router.feed("zh", [{"type": "translation", "text": "你好", "final": False}]) == [
        {"type": "translation", "text": "你好", "final": False}
    ]
