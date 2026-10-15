#!/usr/bin/env python3
"""检查仓库 .env 的密钥，模型列表里有没有 qwen3-tts-flash。"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

TARGET = "qwen3-tts-flash"


def parse_env_text(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:7]}...{key[-4:]}"


def model_ids(payload) -> list[str]:
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    names = []
    for item in rows:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("id"):
            names.append(str(item["id"]))
    return names


def main() -> int:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        print(f"找不到 {env_path}", file=sys.stderr)
        return 2
    env = parse_env_text(env_path.read_text(encoding="utf-8"))
    api_key = env.get("LLM_API_KEY", "")
    base = env.get("LLM_OPEN_AI_URL", "").rstrip("/")
    if not base and env.get("LLM_HOST"):
        base = f"https://{env['LLM_HOST']}/compatible-mode/v1"
    if not api_key or not base:
        print("缺少 LLM_API_KEY 或 LLM_OPEN_AI_URL", file=sys.stderr)
        return 2

    url = f"{base}/models"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    print(f"地址: {url}")
    print(f"密钥: {mask_key(api_key)}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        print(f"模型列表请求失败 HTTP {exc.code}")
        print(detail)
        return 1
    except urllib.error.URLError as exc:
        print(f"连不上模型列表: {exc.reason}")
        return 1

    names = model_ids(payload)
    related = [name for name in names if "tts" in name.lower()]
    print(f"模型总数: {len(names)}")
    if TARGET in names:
        print(f"{TARGET}: 在可用列表中")
        return 0
    print(f"{TARGET}: 不在可用列表中")
    if related:
        print("列表里其他带 tts 的模型:")
        for name in related:
            print(f"  {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
