from online_caption.model_map import CaptionMapper, session_update


def test_source_deltas_append_until_completed():
    mapper = CaptionMapper()
    first = mapper.feed(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "delta": "这个",
        }
    )
    second = mapper.feed(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "delta": "多少钱",
        }
    )
    done = mapper.feed(
        {"type": "conversation.item.input_audio_transcription.completed"}
    )
    assert first == [{"type": "source", "text": "这个", "final": False}]
    assert second == [{"type": "source", "text": "这个多少钱", "final": False}]
    assert done == [{"type": "source", "text": "这个多少钱", "final": True}]


def test_translation_deltas_append_and_next_sentence_starts_empty():
    mapper = CaptionMapper()
    assert mapper.feed({"type": "response.text.delta", "delta": "How "}) == [
        {"type": "translation", "text": "How ", "final": False}
    ]
    assert mapper.feed({"type": "response.text.delta", "delta": "much"}) == [
        {"type": "translation", "text": "How much", "final": False}
    ]
    assert mapper.feed({"type": "response.done"}) == [
        {"type": "translation", "text": "How much", "final": True}
    ]
    assert mapper.feed({"type": "response.text.delta", "delta": "Hello"}) == [
        {"type": "translation", "text": "Hello", "final": False}
    ]


def test_model_error_becomes_upstream_error():
    mapper = CaptionMapper()
    assert mapper.feed({"type": "error", "message": "模型拒绝了这句"}) == [
        {"type": "error", "code": "upstream", "message": "模型拒绝了这句"}
    ]


def test_session_update_is_text_only():
    event = session_update("en")
    assert event["type"] == "session.update"
    assert event["session"]["output_modalities"] == ["text"]
    assert event["session"]["translation"]["language"] == "en"
    assert "audio" not in event["session"]["output_modalities"]

    zh = session_update("zh")
    assert zh["session"]["translation"]["language"] == "zh"
    assert zh["session"]["output_modalities"] == ["text"]
