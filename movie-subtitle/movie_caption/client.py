"""按网页同声协议连接本机网关。"""

import asyncio
import contextlib
import json

from movie_caption.modes import DEFAULT_TARGET, TARGETS

__all__ = [
    "DEFAULT_TARGET",
    "TARGETS",
    "SocketEnded",
    "Target",
    "WebSocketAdapter",
    "exchange",
    "open_gateway",
    "parse_event",
    "run_gateway",
    "start_message",
    "stop_message",
]


class SocketEnded(Exception):
    pass


class Target:
    def __init__(self, value: str) -> None:
        self.value = value


def start_message(target: str) -> str:
    if target not in TARGETS:
        raise ValueError(target)
    return json.dumps({"type": "start", "target": target}, ensure_ascii=False)


def stop_message() -> str:
    return json.dumps({"type": "stop"})


def parse_event(message: str) -> dict | None:
    try:
        event = json.loads(message)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict) or event.get("type") not in ("source", "translation", "error"):
        return None
    return event


class WebSocketAdapter:
    def __init__(self, websocket) -> None:
        self._websocket = websocket

    async def send(self, data) -> None:
        from websockets.exceptions import ConnectionClosed

        try:
            await self._websocket.send(data)
        except ConnectionClosed as exc:
            raise SocketEnded from exc

    async def recv(self):
        from websockets.exceptions import ConnectionClosed

        try:
            return await self._websocket.recv()
        except ConnectionClosed as exc:
            raise SocketEnded from exc

    async def close(self) -> None:
        await self._websocket.close()


async def open_gateway(url: str) -> WebSocketAdapter:
    from websockets.asyncio.client import connect

    return WebSocketAdapter(await connect(url))


async def exchange(socket, target: Target, pull, on_event, stop) -> None:
    current = target.value
    await socket.send(start_message(current))
    while not stop.is_set():
        if target.value != current:
            current = target.value
            await socket.send(start_message(current))
        chunk = pull()
        if chunk is not None:
            await socket.send(chunk)
        try:
            message = await asyncio.wait_for(socket.recv(), 0.05)
        except TimeoutError:
            continue
        if isinstance(message, bytes):
            continue
        event = parse_event(message)
        if event:
            on_event(event)


async def _pause(stop, seconds: float) -> bool:
    if stop.is_set():
        return True
    if seconds <= 0:
        await asyncio.sleep(0)
        return stop.is_set()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while not stop.is_set():
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(0.05, remaining))
    return True


async def run_gateway(connect, target: Target, pull, on_event, stop, retry_seconds: float = 3) -> None:
    while not stop.is_set():
        try:
            socket = await connect()
        except OSError:
            on_event({"type": "error", "code": "upstream", "message": "连不上"})
            if await _pause(stop, retry_seconds):
                return
            continue
        try:
            await exchange(socket, target, pull, on_event, stop)
            return
        except SocketEnded:
            on_event({"type": "error", "code": "upstream", "message": "连接中断"})
        finally:
            with contextlib.suppress(Exception):
                await socket.send(stop_message())
            with contextlib.suppress(Exception):
                await socket.close()
        if await _pause(stop, retry_seconds):
            return
