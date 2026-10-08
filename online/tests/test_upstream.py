import json

import pytest

from online_caption.upstream import (
    AuthError,
    LiveTranslateClient,
    parse_env_text,
    require_settings,
)


def test_missing_settings_name_the_keys_and_hide_the_secret():
    with pytest.raises(RuntimeError) as raised:
        require_settings({"LLM_API_KEY": "sk-secret-value"})
    text = str(raised.value)
    assert "LLM_HOST" in text
    assert "MODEL" in text
    assert "sk-secret-value" not in text


def test_realtime_url_uses_host_and_model_only():
    settings = require_settings(
        {
            "LLM_API_KEY": "sk-secret-value",
            "LLM_HOST": "llm-example.cn-beijing.maas.aliyuncs.com",
            "MODEL": "qwen3.8-livetranslate-flash-realtime",
            "LLM_OPEN_AI_URL": "https://ignored.example/v1",
        }
    )
    assert settings.url == (
        "wss://llm-example.cn-beijing.maas.aliyuncs.com"
        "/api-ws/v1/realtime?model=qwen3.8-livetranslate-flash-realtime"
    )
    assert settings.authorization == "Bearer sk-secret-value"
    assert "ignored.example" not in settings.url


def test_parse_env_text_skips_comments_and_blank_lines():
    env = parse_env_text(
        """
# comment
LLM_HOST=llm-example.cn-beijing.maas.aliyuncs.com

MODEL=qwen3.8-livetranslate-flash-realtime
"""
    )
    assert env == {
        "LLM_HOST": "llm-example.cn-beijing.maas.aliyuncs.com",
        "MODEL": "qwen3.8-livetranslate-flash-realtime",
    }


class FakeSocket:
    def __init__(self, incoming):
        self.sent = []
        self.incoming = list(incoming)
        self.closed = False

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def recv(self):
        return json.dumps(self.incoming.pop(0))

    async def close(self):
        self.closed = True


def test_client_reads_model_events_and_finishes():
    import asyncio

    settings = require_settings(
        {
            "LLM_API_KEY": "sk-secret-value",
            "LLM_HOST": "llm-example.cn-beijing.maas.aliyuncs.com",
            "MODEL": "qwen3.8-livetranslate-flash-realtime",
        }
    )
    socket = FakeSocket(
        [
            {"type": "response.text.delta", "delta": "Hi"},
            {"type": "session.finished"},
        ]
    )
    seen = {}

    async def connector(url, authorization):
        seen["url"] = url
        seen["authorization"] = authorization
        return socket

    async def scenario():
        client = LiveTranslateClient(settings, connector)
        await client.connect()
        events = await client.read()
        await client.finish()
        return events

    events = asyncio.run(scenario())
    assert seen["url"] == settings.url
    assert seen["authorization"] == "Bearer sk-secret-value"
    assert events == [{"type": "translation", "text": "Hi", "final": False}]
    assert socket.sent == [{"type": "session.finish"}]
    assert socket.closed


def test_session_updated_marks_the_client_ready_for_audio():
    import asyncio

    settings = require_settings(
        {
            "LLM_API_KEY": "sk-secret-value",
            "LLM_HOST": "llm-example.cn-beijing.maas.aliyuncs.com",
            "MODEL": "qwen3.8-livetranslate-flash-realtime",
        }
    )
    socket = FakeSocket([{"type": "session.updated", "session": {}}])

    async def connector(url, authorization):
        return socket

    async def scenario():
        client = LiveTranslateClient(settings, connector)
        await client.connect()
        assert client.ready is False
        await client.read()
        assert client.ready is True

    asyncio.run(scenario())


def test_auth_failure_hides_the_key():
    import asyncio

    settings = require_settings(
        {
            "LLM_API_KEY": "sk-secret-value",
            "LLM_HOST": "llm-example.cn-beijing.maas.aliyuncs.com",
            "MODEL": "qwen3.8-livetranslate-flash-realtime",
        }
    )

    class Denied(Exception):
        status = 401

    async def connector(url, authorization):
        raise Denied("401 sk-secret-value")

    async def scenario():
        client = LiveTranslateClient(settings, connector)
        await client.connect()

    with pytest.raises(AuthError) as raised:
        asyncio.run(scenario())
    assert "sk-secret-value" not in str(raised.value)
    assert "鉴权失败" in str(raised.value)
