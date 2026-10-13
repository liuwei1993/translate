import argparse
import asyncio
import queue
import threading

from movie_caption.audio import feed_wav
from movie_caption.client import Target, open_gateway, run_gateway
from movie_caption.loopback import capture_into
from movie_caption.modes import DEFAULT_TARGET, TARGETS
from movie_caption.overlay import CaptionWindow


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="把正在播放的电影声音译成中日字幕")
    parser.add_argument("--gateway", default="ws://127.0.0.1:9000/ws")
    parser.add_argument("--target", choices=TARGETS, default=DEFAULT_TARGET)
    parser.add_argument("--wav", help="用 16 bit wav 代替扬声器回环")
    args = parser.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    target = Target(args.target)
    stop = threading.Event()
    pcm = queue.Queue()
    window = CaptionWindow(target, on_close=stop.set)

    def pull():
        try:
            return pcm.get_nowait()
        except queue.Empty:
            return None

    def runner() -> None:
        asyncio.run(
            run_gateway(
                lambda: open_gateway(args.gateway),
                target,
                pull,
                window.post,
                stop,
            )
        )

    worker = threading.Thread(target=runner, name="movie-gateway", daemon=True)
    worker.start()
    if args.wav:
        feeder = threading.Thread(target=feed_wav, args=(args.wav, pcm, stop), name="movie-wav", daemon=True)
    else:
        feeder = threading.Thread(
            target=capture_into,
            args=(pcm, window.post, stop),
            name="movie-loopback",
            daemon=True,
        )
    feeder.start()
    window.show()
    app.exec()
    stop.set()
    feeder.join(timeout=1)
    worker.join(timeout=1)


if __name__ == "__main__":
    main()
