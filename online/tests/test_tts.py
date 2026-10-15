import json

import pytest

from online_caption.tts import TtsRejected, TtsUpstream, language_type_for, request_body, speak
from online_caption.upstream import Settings


def settings() -> Settings:
    return Settings(api_key="sk-secret-value", host="llm.example", model="realtime-model")


def test_language_type_follows_the_script():
    assert language_type_for("你好") == "Chinese"
    assert language_type_for("Hello") == "English"
    assert language_type_for("こんにちは") == "Japanese"
    assert language_type_for("20") == "Auto"


def test_request_uses_flash_model_and_cherry():
    body = request_body("你好")
    assert body == {
        "model": "qwen3-tts-flash",
        "input": {
            "text": "你好",
            "voice": "Cherry",
            "language_type": "Chinese",
        },
    }


def test_speak_downloads_the_wav_from_the_returned_url():
    seen = {}

    def post(url, headers, body):
        seen["url"] = url
        seen["headers"] = headers
        seen["body"] = json.loads(body)
        payload = {"output": {"audio": {"url": "https://audio.example/a.wav", "data": ""}}}
        return 200, json.dumps(payload).encode()

    def download(url):
        seen["audio"] = url
        return 200, b"RIFF-wav"

    result = speak(settings(), "/tts?text=%E4%BD%A0%E5%A5%BD", post=post, download=download)

    assert result.status == 200
    assert result.content_type == "audio/wav"
    assert result.body == b"RIFF-wav"
    assert seen["url"] == (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    )
    assert seen["headers"]["Authorization"] == "Bearer sk-secret-value"
    assert seen["body"]["model"] == "qwen3-tts-flash"
    assert seen["body"]["input"]["text"] == "你好"
    assert "sk-secret-value" not in json.dumps(seen["body"])
    assert seen["audio"] == "https://audio.example/a.wav"


def test_empty_and_long_text_never_call_upstream():
    def post(url, headers, body):
        raise AssertionError("should not post")

    empty = speak(settings(), "/tts?text=", post=post, download=post)
    blank = speak(settings(), "/tts?text=%20%20", post=post, download=post)
    long = speak(settings(), "/tts?text=" + "啊" * 601, post=post, download=post)

    assert empty.status == 400
    assert empty.body == "没有文字".encode()
    assert blank.status == 400
    assert long.status == 400
    assert long.body == "这句话太长".encode()
    assert "sk-secret-value" not in empty.body.decode()


def test_upstream_failure_is_a_fixed_chinese_message():
    def post(url, headers, body):
        return 401, json.dumps({"message": "bad key sk-secret-value"}).encode()

    result = speak(settings(), "/tts?text=Hello", post=post, download=post)

    assert result.status == 502
    assert result.body == "朗读失败".encode()
    assert b"sk-secret-value" not in result.body


def test_http_and_localhost_audio_urls_are_rejected():
    def post_http(url, headers, body):
        return 200, json.dumps({"output": {"audio": {"url": "http://audio.example/a.wav"}}}).encode()

    def post_local(url, headers, body):
        return 200, json.dumps({"output": {"audio": {"url": "https://127.0.0.1/a.wav"}}}).encode()

    def download(url):
        raise AssertionError("should not download")

    http_result = speak(settings(), "/tts?text=Hello", post=post_http, download=download)
    local_result = speak(settings(), "/tts?text=Hello", post=post_local, download=download)
    assert http_result.status == 502
    assert local_result.status == 502


def test_oversized_wav_is_upstream_failure():
    def post(url, headers, body):
        return 200, json.dumps({"output": {"audio": {"url": "https://audio.example/a.wav"}}}).encode()

    def download(url):
        return 200, b"x" * (2_000_001)

    result = speak(settings(), "/tts?text=Hello", post=post, download=download)
    assert result.status == 502
    assert result.body == "朗读失败".encode()


def test_missing_audio_url_is_upstream_failure():
    def post(url, headers, body):
        return 200, json.dumps({"output": {"audio": {"data": ""}}}).encode()

    result = speak(settings(), "/tts?text=Hello", post=post, download=post)
    assert result.status == 502
    assert result.body == "朗读失败".encode()


def test_rejected_and_upstream_types_keep_their_status():
    assert TtsRejected("没有文字").status == 400
    assert TtsUpstream().status == 502
    with pytest.raises(TtsUpstream):
        raise TtsUpstream()
