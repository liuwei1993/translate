"""把一行字幕交给 qwen3-tts-flash，取回 wav。密钥只出现在请求头里。"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from online_caption.direction import speech_language

MODEL = "qwen3-tts-flash"
VOICE = "Cherry"
MAX_CHARS = 600
MAX_WAV_BYTES = 2_000_000
# 业务空间域名不提供这条合成接口，Qwen-TTS 走北京 DashScope。
DASHSCOPE_HOST = "dashscope.aliyuncs.com"
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


def audio_url(payload: dict) -> str:
    output = payload.get("output") or {}
    audio = output.get("audio") or {}
    url = audio.get("url") or ""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or _blocked_audio_host(host):
        raise TtsUpstream()
    return url


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


def _read(request: urllib.request.Request) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError:
        raise TtsUpstream() from None


def post_json(url: str, headers: dict, body: bytes) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    return _read(request)


def download_bytes(url: str) -> tuple[int, bytes]:
    return _read(urllib.request.Request(url, method="GET"))


def speak(settings, raw_path: str, post, download) -> SpeakResult:
    try:
        wav = synthesize(settings, query_text(raw_path), post, download)
    except TtsRejected as exc:
        return SpeakResult(exc.status, "text/plain; charset=utf-8", exc.message.encode())
    except TtsUpstream as exc:
        return SpeakResult(exc.status, "text/plain; charset=utf-8", exc.message.encode())
    return SpeakResult(200, "audio/wav", wav)
