import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from movie_caption.client import Target
from movie_caption.overlay import CaptionWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_window_shows_the_japanese_translation(qapp):
    window = CaptionWindow(Target("ja-auto"))
    window.post({"type": "source", "text": "こんにちは", "final": False})
    window.post({"type": "translation", "text": "你好", "final": True})
    window.show()
    qapp.processEvents()
    assert window.lines.big_text() == "你好"
    image = window.grab()
    assert not image.isNull()
    assert image.width() > 10


def test_closing_the_window_quits_the_application(qapp, monkeypatch):
    quit_called = {"yes": False}
    monkeypatch.setattr(qapp, "quit", lambda: quit_called.__setitem__("yes", True))
    closed = {"yes": False}
    window = CaptionWindow(Target("ja-auto"), on_close=lambda: closed.__setitem__("yes", True))
    window.close()
    assert closed["yes"] is True
    assert quit_called["yes"] is True


def test_switching_direction_clears_the_current_line(qapp):
    window = CaptionWindow(Target("ja-auto"))
    window.post({"type": "translation", "text": "你好", "final": True})
    window.choose("ja2zh")
    assert window.target.value == "ja2zh"
    assert window.lines.translation == ""
    assert window.lines.big_text() == "等待字幕"
