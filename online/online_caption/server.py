"""HTTPS 页面和浏览器 WebSocket。模型密钥不出这个进程。"""

import argparse
import asyncio
import contextlib
import json
import logging
import socket
import ssl
import subprocess
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

from online_caption.direction import CaptionRouter
from online_caption.gateway import GatewaySession
from online_caption.model_map import session_update
from online_caption.upstream import (
    AuthError,
    LiveTranslateClient,
    load_settings,
)

logger = logging.getLogger("online_caption")

WEB_ROOT = Path(__file__).resolve().parents[1] / "web"
CERT_DIR = Path(__file__).resolve().parents[1] / "certs"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


def resolve_web_file(web_root: Path, url_path: str) -> Path | None:
    path = url_path.split("?", 1)[0]
    if path in ("", "/"):
        path = "/index.html"
    candidate = (web_root / path.lstrip("/")).resolve()
    try:
        candidate.relative_to(web_root.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def local_ips() -> list[str]:
    ips = {"127.0.0.1"}
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ips.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    return sorted(ips)


def ensure_certificate(cert_dir: Path) -> tuple[Path, Path]:
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"
    if cert_path.is_file() and key_path.is_file():
        return cert_path, key_path
    san = ",".join(["DNS:localhost", *[f"IP:{ip}" for ip in local_ips()]])
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-days",
            "365",
            "-nodes",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-subj",
            "/CN=online-caption",
            "-addext",
            f"subjectAltName={san}",
        ],
        check=True,
        capture_output=True,
    )
    return cert_path, key_path


def http_file(status: int, body: bytes, content_type: str) -> Response:
    headers = Headers(
        [
            ("Connection", "close"),
            ("Content-Length", str(len(body))),
            ("Content-Type", content_type),
            ("Cache-Control", "no-store"),
        ]
    )
    reason = "OK" if status == 200 else "Not Found"
    return Response(status, reason, headers, body)


class BrowserBridge:
    def __init__(self, settings) -> None:
        self._settings = settings

    async def __call__(self, websocket) -> None:
        session = GatewaySession()
        clients: dict[str, LiveTranslateClient] = {}
        readers: list[asyncio.Task] = []
        pending_audio: list[bytes] = []
        router = CaptionRouter()

        async def send_browser(events: list[dict]) -> None:
            for event in events:
                await websocket.send(json.dumps(event, ensure_ascii=False))

        async def cancel_readers() -> None:
            nonlocal readers
            current = readers
            readers = []
            for task in current:
                task.cancel()
            for task in current:
                with contextlib.suppress(asyncio.CancelledError, ConnectionClosed, Exception):
                    await task

        async def close_client(current: LiveTranslateClient | None, finish_event: dict | None) -> None:
            if current is None:
                return
            try:
                if finish_event is not None:
                    await current.send_event(finish_event)
                    await asyncio.wait_for(current.finish(send=False), timeout=8)
                else:
                    await current.aclose()
            except Exception:
                logger.info("关闭模型连接")
                with contextlib.suppress(Exception):
                    await current.aclose()

        def lanes_ready() -> bool:
            return bool(clients) and all(item.ready for item in clients.values())

        async def flush_audio() -> None:
            while pending_audio and lanes_ready():
                chunk = pending_audio.pop(0)
                for event in session.audio(chunk):
                    for item in clients.values():
                        await item.send_event(event)

        async def pump(lane: str, current: LiveTranslateClient) -> None:
            try:
                while True:
                    events = await current.read()
                    if lanes_ready():
                        await flush_audio()
                    events = router.feed(lane, events)
                    if events:
                        await send_browser(events)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.info("模型连接中断")
                clients.pop(lane, None)
                if clients:
                    return
                with contextlib.suppress(Exception):
                    await send_browser(session.disconnect())

        async def open_client() -> LiveTranslateClient | None:
            import websockets

            async def connector(url: str, authorization: str):
                return await websockets.connect(
                    url,
                    additional_headers={"Authorization": authorization},
                )

            current = LiveTranslateClient(self._settings, connector)
            try:
                await current.connect()
            except AuthError:
                logger.info("鉴权失败")
                await send_browser(
                    [{"type": "error", "code": "auth", "message": "鉴权失败"}]
                )
                return None
            except Exception:
                logger.info("连不上模型")
                await send_browser(
                    [{"type": "error", "code": "upstream", "message": "连不上服务器"}]
                )
                return None
            return current

        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    if not clients:
                        continue
                    if not lanes_ready():
                        pending_audio.append(message)
                        continue
                    try:
                        await flush_audio()
                        for event in session.audio(message):
                            for item in clients.values():
                                await item.send_event(event)
                    except Exception:
                        logger.info("发送音频失败")
                        await cancel_readers()
                        dead = list(clients.values())
                        clients.clear()
                        for item in dead:
                            await close_client(item, None)
                        await send_browser(session.disconnect())
                    continue
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue
                kind = payload.get("type")
                if kind == "start":
                    raw_target = payload.get("target") or "auto"
                    if raw_target not in ("auto", "en", "zh"):
                        await send_browser(
                            [{"type": "error", "code": "upstream", "message": "方向不对"}]
                        )
                        continue
                    if clients:
                        await cancel_readers()
                        finish_event = {"type": "session.finish"}
                        for item in list(clients.values()):
                            await close_client(item, finish_event)
                        clients.clear()
                        session.stop()
                    router.set_mode(raw_target)
                    pending_audio.clear()
                    opened: dict[str, LiveTranslateClient] = {}
                    for lane in ("en", "zh"):
                        current = await open_client()
                        if current is None:
                            for item in opened.values():
                                await close_client(item, None)
                            session.stop()
                            opened = {}
                            break
                        await current.send_event(session_update(lane))
                        opened[lane] = current
                    if not opened:
                        continue
                    session.open_for_auto()
                    clients.update(opened)
                    for lane, item in opened.items():
                        readers.append(asyncio.create_task(pump(lane, item)))
                elif kind == "stop":
                    outgoing = session.stop()
                    await cancel_readers()
                    finish_event = outgoing[0] if outgoing else None
                    for item in list(clients.values()):
                        await close_client(item, finish_event)
                    clients.clear()
        except ConnectionClosed:
            pass
        finally:
            await cancel_readers()
            outgoing = session.stop()
            finish_event = outgoing[0] if outgoing else None
            for item in list(clients.values()):
                await close_client(item, finish_event)


async def process_request(connection, request):
    if request.path.split("?", 1)[0] == "/ws":
        return None
    file_path = resolve_web_file(WEB_ROOT, request.path)
    if file_path is None:
        return http_file(404, "找不到页面".encode(), "text/plain; charset=utf-8")
    content_type = CONTENT_TYPES.get(file_path.suffix, "application/octet-stream")
    return http_file(200, file_path.read_bytes(), content_type)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="用 HTTP 和 ws，不启用证书")
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    settings = load_settings()
    ssl_context = None
    scheme = "http"
    port = args.port if args.port is not None else 9000
    if not args.http:
        cert_path, key_path = ensure_certificate(CERT_DIR)
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(cert_path, key_path)
        scheme = "https"
        if args.port is None:
            port = 8443
    bridge = BrowserBridge(settings)
    async with serve(
        bridge,
        "0.0.0.0",
        port,
        process_request=process_request,
        ssl=ssl_context,
        max_size=2**20,
    ):
        for ip in local_ips():
            logger.info("打开 %s://%s:%s", scheme, ip, port)
        if scheme == "https":
            logger.info("手机第一次打开时，在 Chrome 里继续前往这个不受信任的证书。")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
