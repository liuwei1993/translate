import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from online_caption.tts import (
    TtsRejected,
    TtsUpstream,
    download_bytes,
    language_type_for,
    post_json,
    request_body,
    speak,
)
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
        payload = {
            "output": {
                "audio": {
                    "url": "https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/a.wav",
                    "data": "",
                }
            }
        }
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
    assert seen["audio"] == "https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/a.wav"


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


def test_http_audio_url_is_fetched_over_https():
    seen = []

    def post(url, headers, body):
        return 200, json.dumps(
            {"output": {"audio": {"url": "http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/a.wav"}}}
        ).encode()

    def download(url):
        seen.append(url)
        return 200, b"RIFF-wav"

    result = speak(settings(), "/tts?text=Hello", post=post, download=download)
    assert result.status == 200
    assert result.body == b"RIFF-wav"
    assert seen == ["https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/a.wav"]


def test_non_aliyun_and_loopback_audio_urls_are_rejected():
    urls = [
        "https://audio.example/a.wav",
        "https://127.0.0.1/a.wav",
        "http://127.0.0.1/a.wav",
        "http://2130706433/a.wav",
        "https://localhost.localdomain/a.wav",
    ]

    def download(url):
        raise AssertionError("should not download")

    for url in urls:
        def post(url, headers, body, audio_url=url):
            return 200, json.dumps({"output": {"audio": {"url": audio_url}}}).encode()

        result = speak(settings(), "/tts?text=Hello", post=post, download=download)
        assert result.status == 502


def test_oversized_wav_is_upstream_failure():
    def post(url, headers, body):
        return 200, json.dumps(
            {"output": {"audio": {"url": "https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/a.wav"}}}
        ).encode()

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


def _serve(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_authenticated_post_does_not_follow_redirects():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["auth"] = self.headers.get("Authorization")
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{server.server_address[1]}/steal")
            self.end_headers()

        def do_GET(self):
            seen["followed"] = self.path
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = _serve(Handler)
    try:
        with pytest.raises(TtsUpstream):
            post_json(
                f"http://127.0.0.1:{server.server_address[1]}/generation",
                {"Authorization": "Bearer sk-secret-value", "Content-Type": "application/json"},
                b"{}",
            )
    finally:
        server.shutdown()
    assert seen["path"] == "/generation"
    assert seen["auth"] == "Bearer sk-secret-value"
    assert "followed" not in seen


def test_audio_redirect_to_loopback_is_not_fetched():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen[self.path] = self.headers.get("Authorization")
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{server.server_address[1]}/secret.wav")
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = _serve(Handler)
    try:
        with pytest.raises(TtsUpstream):
            download_bytes(f"http://127.0.0.1:{server.server_address[1]}/audio.wav")
    finally:
        server.shutdown()
    assert seen["/audio.wav"] is None
    assert "/secret.wav" not in seen


def test_rejected_and_upstream_types_keep_their_status():
    assert TtsRejected("没有文字").status == 400
    assert TtsUpstream().status == 502
    with pytest.raises(TtsUpstream):
        raise TtsUpstream()
