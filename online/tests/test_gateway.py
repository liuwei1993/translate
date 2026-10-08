import base64

from online_caption.gateway import GatewaySession
from online_caption.model_map import session_update


def test_start_sends_text_only_session_update():
    session = GatewaySession()
    assert session.start("en") == [session_update("en")]


def test_audio_frame_becomes_base64_append():
    session = GatewaySession()
    session.start("en")
    pcm = b"\x01\x00\x02\x00"
    assert session.audio(pcm) == [
        {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm).decode("ascii"),
        }
    ]


def test_upstream_deltas_become_full_caption_text():
    session = GatewaySession()
    session.start("en")
    assert session.ingest(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "delta": "这个",
        }
    ) == [{"type": "source", "text": "这个", "final": False}]
    assert session.ingest(
        {"type": "response.text.delta", "delta": "How much"}
    ) == [{"type": "translation", "text": "How much", "final": False}]


def test_second_start_finishes_previous_and_drops_unfrozen_text():
    session = GatewaySession()
    session.start("en")
    session.ingest(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "delta": "这个",
        }
    )
    outgoing = session.start("zh")
    assert outgoing[0] == {"type": "session.finish"}
    assert outgoing[1] == session_update("zh")
    assert all(event.get("type") != "source" for event in outgoing)
    assert session.ingest(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "delta": "Hello",
        }
    ) == [{"type": "source", "text": "Hello", "final": False}]


def test_disconnect_keeps_final_captions_and_reports_error():
    session = GatewaySession()
    session.start("en")
    emitted = session.ingest(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "delta": "这个多少钱",
        }
    )
    emitted += session.ingest(
        {"type": "conversation.item.input_audio_transcription.completed"}
    )
    emitted += session.disconnect()
    assert {"type": "source", "text": "这个多少钱", "final": True} in emitted
    assert emitted[-1] == {
        "type": "error",
        "code": "upstream",
        "message": "连接中断",
    }
