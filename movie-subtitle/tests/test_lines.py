from movie_caption.lines import CaptionLines


def test_partial_source_keeps_the_current_translation():
    lines = CaptionLines()
    lines.apply({"type": "source", "text": "こん", "final": False})
    lines.apply({"type": "translation", "text": "你", "final": False})
    lines.apply({"type": "source", "text": "こんにちは", "final": False})
    assert lines.source == "こんにちは"
    assert lines.translation == "你"


def test_new_source_clears_the_previous_translation():
    lines = CaptionLines()
    lines.apply({"type": "source", "text": "こんにちは", "final": True})
    lines.apply({"type": "translation", "text": "你好", "final": True})
    lines.apply({"type": "source", "text": "次", "final": False})
    assert lines.source == "次"
    assert lines.translation == ""


def test_empty_translation_clears_the_line():
    lines = CaptionLines()
    lines.apply({"type": "translation", "text": "你好", "final": True})
    lines.apply({"type": "translation", "text": "", "final": False})
    assert lines.translation == ""
    assert lines.big_text() == "等待字幕"


def test_error_stays_visible_without_erasing_the_translation():
    lines = CaptionLines()
    lines.apply({"type": "source", "text": "こんにちは", "final": False})
    lines.apply({"type": "translation", "text": "你好", "final": True})
    lines.apply({"type": "error", "code": "auth", "message": "鉴权失败"})
    assert lines.translation == "你好"
    assert lines.big_text() == "鉴权失败"
    lines.apply({"type": "translation", "text": "你好啊", "final": False})
    assert lines.big_text() == "你好啊"
