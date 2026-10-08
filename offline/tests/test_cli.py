import json

from offline_caption.cli import format_caption


def test_format_caption_is_one_json_object():
    line = format_caption({"source": "这个多少钱", "translation": "How much is this?", "final": True})
    assert json.loads(line) == {
        "source": "这个多少钱",
        "translation": "How much is this?",
        "final": True,
    }
