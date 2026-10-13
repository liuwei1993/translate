import asyncio
import json

import pytest

from movie_caption.client import (
    SocketEnded,
    Target,
    WebSocketAdapter,
    exchange,
    parse_event,
    run_gateway,
    start_message,
    stop_message,
)
from movie_caption.lines import CaptionLines
from movie_caption.modes import DEFAULT_TARGET, TARGETS


def test_default_target_is_chinese_japanese():
    assert DEFAULT_TARGET == "ja-auto"
    assert TARGETS == ("ja-auto", "ja", "ja2zh")
    assert json.loads(start_message("ja2zh")) == {"type": "start", "target": "ja2zh"}
    assert json.loads(start_message("ja")) == {"type": "start", "target": "ja"}
    assert json.loads(stop_message()) == {"type": "stop"}


def test_english_target_is_rejected():
    try:
        start_message("zh")
    except ValueError:
        return
    raise AssertionError("英文方向不应从电影字幕发出")


def test_parse_event_keeps_caption_and_drops_noise():
    event = parse_event('{"type":"translation","text":"你好","final":true}')
    assert event == {"type": "translation", "text": "你好", "final": True}
    assert parse_event("not-json") is None
    assert parse_event('{"type":"session.updated"}') is None


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.incoming = asyncio.Queue()
        self.closed = False

    async def send(self, data):
        self.sent.append(data)

    async def recv(self):
        item = await self.incoming.get()
        if item is SocketEnded:
            raise SocketEnded
        return item

    async def close(self):
        self.closed = True


def test_exchange_sends_japanese_start_and_pcm():
    async def scenario():
        socket = FakeSocket()
        lines = CaptionLines()
        target = Target("ja2zh")
        stop = asyncio.Event()
        chunks = iter([b"\x01\x00" * 1600])

        def pull():
            try:
                return next(chunks)
            except StopIteration:
                return None

        def on_event(event):
            lines.apply(event)
            if event.get("type") == "translation" and event.get("final"):
                stop.set()

        task = asyncio.create_task(exchange(socket, target, pull, on_event, stop))
        await socket.incoming.put(
            json.dumps({"type": "source", "text": "こんにちは", "final": False}, ensure_ascii=False)
        )
        await socket.incoming.put(
            json.dumps({"type": "translation", "text": "你好", "final": True}, ensure_ascii=False)
        )
        await task
        assert json.loads(socket.sent[0]) == {"type": "start", "target": "ja2zh"}
        assert socket.sent[1] == b"\x01\x00" * 1600
        assert lines.source == "こんにちは"
        assert lines.translation == "你好"

    asyncio.run(scenario())


def test_direction_change_sends_a_new_start():
    async def scenario():
        socket = FakeSocket()
        target = Target("ja2zh")
        stop = asyncio.Event()
        calls = {"n": 0}

        def pull():
            calls["n"] += 1
            if calls["n"] == 2:
                target.value = "ja-auto"
            if calls["n"] > 4:
                stop.set()
            return None

        await exchange(socket, target, pull, lambda event: None, stop)
        starts = [json.loads(item)["target"] for item in socket.sent if isinstance(item, str)]
        assert starts == ["ja2zh", "ja-auto"]

    asyncio.run(scenario())


class DeadSocket(FakeSocket):
    async def recv(self):
        raise SocketEnded


def test_reconnects_after_the_gateway_is_down():
    async def scenario():
        notices = []
        stop = asyncio.Event()
        sockets = []

        async def connect():
            connect.n += 1
            if connect.n == 1:
                raise OSError("refused")
            socket = DeadSocket()
            sockets.append(socket)
            return socket

        connect.n = 0

        def on_event(event):
            notices.append(event["message"])
            if event["message"] == "连接中断":
                stop.set()

        await run_gateway(
            connect,
            Target("ja-auto"),
            lambda: None,
            on_event,
            stop,
            retry_seconds=0,
        )
        assert notices == ["连不上", "连接中断"]
        assert json.loads(sockets[0].sent[0])["target"] == "ja-auto"
        assert json.loads(sockets[0].sent[-1]) == {"type": "stop"}

    asyncio.run(scenario())


def test_websocket_adapter_round_trip():
    pytest.importorskip("websockets.asyncio.server")

    async def scenario():
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        seen = {}

        async def handler(websocket):
            seen["start"] = json.loads(await websocket.recv())
            seen["pcm"] = await websocket.recv()
            await websocket.send(
                json.dumps({"type": "source", "text": "こんにちは", "final": False}, ensure_ascii=False)
            )
            await websocket.send(
                json.dumps({"type": "translation", "text": "你好", "final": True}, ensure_ascii=False)
            )
            try:
                await websocket.recv()
            except Exception:
                return

        lines = CaptionLines()
        stop = asyncio.Event()
        chunks = iter([b"\x00\x01" * 1600])

        def pull():
            try:
                return next(chunks)
            except StopIteration:
                return None

        def on_event(event):
            lines.apply(event)
            if event.get("type") == "translation" and event.get("final"):
                stop.set()

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}") as websocket:
                await exchange(WebSocketAdapter(websocket), Target("ja-auto"), pull, on_event, stop)
        assert seen["start"] == {"type": "start", "target": "ja-auto"}
        assert seen["pcm"] == b"\x00\x01" * 1600
        assert lines.source == "こんにちは"
        assert lines.translation == "你好"

    asyncio.run(scenario())
