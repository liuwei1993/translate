"""连接百炼 LiveTranslate。密钥只出现在握手头里。"""

import json
from dataclasses import dataclass
from pathlib import Path

from online_caption.model_map import CaptionMapper


class AuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    api_key: str
    host: str
    model: str

    @property
    def url(self) -> str:
        return f"wss://{self.host}/api-ws/v1/realtime?model={self.model}"

    @property
    def authorization(self) -> str:
        return f"Bearer {self.api_key}"


def require_settings(env: dict) -> Settings:
    missing = [
        name
        for name in ("LLM_API_KEY", "LLM_HOST", "MODEL")
        if not env.get(name)
    ]
    if missing:
        raise RuntimeError("缺少环境变量: " + ", ".join(missing))
    return Settings(
        api_key=env["LLM_API_KEY"],
        host=env["LLM_HOST"],
        model=env["MODEL"],
    )


def parse_env_text(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def repo_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def load_settings(path: Path | None = None) -> Settings:
    import os

    file_env = {}
    env_path = path if path is not None else repo_env_path()
    if env_path.is_file():
        file_env = parse_env_text(env_path.read_text(encoding="utf-8"))
    merged = dict(file_env)
    for name in ("LLM_API_KEY", "LLM_HOST", "MODEL"):
        if os.environ.get(name):
            merged[name] = os.environ[name]
    return require_settings(merged)


class LiveTranslateClient:
    def __init__(self, settings: Settings, connector, mapper=None) -> None:
        self.settings = settings
        self._connector = connector
        self._ws = None
        self._mapper = mapper if mapper is not None else CaptionMapper()
        self.ready = False

    async def connect(self) -> None:
        try:
            self._ws = await self._connector(
                self.settings.url, self.settings.authorization
            )
        except Exception as exc:
            status = getattr(exc, "status", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            if status == 401 or "401" in str(exc):
                raise AuthError("鉴权失败") from None
            raise

    async def send_event(self, event: dict) -> None:
        await self._ws.send(json.dumps(event, ensure_ascii=False))

    async def read(self) -> list[dict]:
        raw = await self._ws.recv()
        event = json.loads(raw)
        if event.get("type") == "session.updated":
            self.ready = True
        return self._mapper.feed(event)

    async def finish(self, *, send: bool = True) -> None:
        if send:
            await self.send_event({"type": "session.finish"})
        while True:
            raw = await self._ws.recv()
            event = json.loads(raw)
            if event.get("type") == "session.finished":
                await self._ws.close()
                return
            if event.get("type") == "error":
                await self._ws.close()
                raise RuntimeError("结束会话失败")

    async def aclose(self) -> None:
        if self._ws is not None:
            await self._ws.close()
