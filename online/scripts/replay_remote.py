"""把本地 16 kHz 录音送到已部署的网页网关，打印字幕事件。"""

import argparse
import asyncio
import json
import wave

import websockets


async def replay(url: str, wav_path: str) -> None:
    async with websockets.connect(url, open_timeout=15, max_size=2**20) as socket:
        await socket.send(json.dumps({"type": "start"}))
        async def send_audio() -> None:
            with wave.open(wav_path) as audio:
                while True:
                    chunk = audio.readframes(1600)
                    if not chunk:
                        break
                    if len(chunk) < 3200:
                        chunk += b"\x00" * (3200 - len(chunk))
                    await socket.send(chunk)
                    await asyncio.sleep(0.1)
            silence = b"\x00" * 3200
            for _ in range(12):
                await socket.send(silence)
                await asyncio.sleep(0.1)
            await asyncio.sleep(4)
            await socket.send(json.dumps({"type": "stop"}))

        sender = asyncio.create_task(send_audio())
        try:
            while True:
                raw = await asyncio.wait_for(socket.recv(), timeout=20)
                if isinstance(raw, bytes):
                    continue
                event = json.loads(raw)
                kind = event.get("type")
                if kind in ("source", "translation"):
                    mark = "定稿" if event.get("final") else "增量"
                    print(f"{kind:12} {mark} {event.get('text')}")
                else:
                    print(kind, event.get("message", ""))
                if kind == "error" and event.get("message") == "连接中断":
                    break
        except asyncio.TimeoutError:
            print("超时，没有更多字幕")
        await sender


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://8.130.163.41:9000/ws")
    parser.add_argument("wav")
    args = parser.parse_args()
    asyncio.run(replay(args.url, args.wav))


if __name__ == "__main__":
    main()
