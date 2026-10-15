"""把一行字幕交给 qwen3-tts-flash，取回 wav。密钥只出现在请求头里。"""

import http.client
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit, urlunsplit

from online_caption.direction import speech_language

MODEL = "qwen3-tts-flash"
VOICE = "Cherry"
MAX_CHARS = 600
MAX_WAV_BYTES = 2_000_000
# 业务空间域名不提供这条合成接口，Qwen-TTS 走北京 DashScope。
DASHSCOPE_HOST = "dashscope.aliyuncs.com"
AUDIO_HOST_SUFFIX = ".aliyuncs.com"
LANGUAGE_TYPE = {"zh": "Chinese", "en": "English", "ja": "Japanese"}


class TtsRejected(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.status = 400
        self.message = message


class TtsUpstream(Exception):
    def __init__(self) -> None:
        super().__init__("朗读失败")
        self.status = 502
        self.message = "朗读失败"


@dataclass(frozen=True)
class SpeakResult:
    status: int
    content_type: str
    body: bytes


def language_type_for(text: str) -> str:
    code = speech_language(text, ("en", "zh", "ja"))
    return LANGUAGE_TYPE.get(code or "", "Auto")


def request_body(text: str) -> dict:
    return {
        "model": MODEL,
        "input": {
            "text": text,
            "voice": VOICE,
            "language_type": language_type_for(text),
        },
    }


def generation_url() -> str:
    return f"https://{DASHSCOPE_HOST}/api/v1/services/aigc/multimodal-generation/generation"


def query_text(raw_path: str) -> str:
    values = parse_qs(urlsplit(raw_path).query, keep_blank_values=True)
    return values.get("text", [""])[0].strip()


def _blocked_audio_host(host: str) -> bool:
    if not host or host == "localhost" or host.endswith(".local") or ":" in host:
        return True
    pieces = host.split(".")
    if len(pieces) != 4:
        return False
    return all(piece.isdigit() and 0 <= int(piece) <= 255 for piece in pieces)


def checked_audio_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme == "http":
        parts = parts._replace(scheme="https")
    host = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme != "https"
        or not host.endswith(AUDIO_HOST_SUFFIX)
        or _blocked_audio_host(host)
    ):
        raise TtsUpstream()
    return urlunsplit(parts)


def audio_url(payload: dict) -> str:
    output = payload.get("output") or {}
    audio = output.get("audio") or {}
    return checked_audio_url(audio.get("url") or "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TtsUpstream()


class _AudioRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return urllib.request.Request(checked_audio_url(newurl), method="GET")


_POST_OPENER = urllib.request.build_opener(_NoRedirect)
_GET_OPENER = urllib.request.build_opener(_AudioRedirect)


def synthesize(settings, text: str, post, download) -> bytes:
    if not text:
        raise TtsRejected("没有文字")
    if len(text) > MAX_CHARS:
        raise TtsRejected("这句话太长")
    body = json.dumps(request_body(text), ensure_ascii=False).encode()
    headers = {
        "Authorization": settings.authorization,
        "Content-Type": "application/json",
    }
    status, raw = post(generation_url(), headers, body)
    if status != 200:
        raise TtsUpstream()
    try:
        payload = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TtsUpstream() from None
    url = audio_url(payload)
    audio_status, wav = download(url)
    if audio_status != 200 or not wav or len(wav) > MAX_WAV_BYTES:
        raise TtsUpstream()
    return wav


def _open(opener, request: urllib.request.Request) -> tuple[int, bytes]:
    try:
        with opener.open(request, timeout=30) as response:
            status = response.status
            body = response.read(MAX_WAV_BYTES + 1)
    except TtsUpstream:
        raise
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise TtsUpstream() from None
    if len(body) > MAX_WAV_BYTES:
        raise TtsUpstream()
    return status, body


def post_json(url: str, headers: dict, body: bytes) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    return _open(_POST_OPENER, request)


def download_bytes(url: str) -> tuple[int, bytes]:
    return _open(_GET_OPENER, urllib.request.Request(url, method="GET"))


def speak(settings, raw_path: str, post, download) -> SpeakResult:
    try:
        wav = synthesize(settings, query_text(raw_path), post, download)
    except TtsRejected as exc:
        return SpeakResult(exc.status, "text/plain; charset=utf-8", exc.message.encode())
    except TtsUpstream as exc:
        return SpeakResult(exc.status, "text/plain; charset=utf-8", exc.message.encode())
    return SpeakResult(200, "audio/wav", wav)
