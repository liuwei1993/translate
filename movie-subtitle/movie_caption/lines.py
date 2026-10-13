"""把网页字幕事件收成当前一行原文和译文。"""


class CaptionLines:
    def __init__(self) -> None:
        self.source = ""
        self.translation = ""
        self.notice = ""

    def apply(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "source":
            text = event.get("text") or ""
            fresh = bool(self.source) and not text.startswith(self.source)
            self.source = text
            if fresh:
                self.translation = ""
            self.notice = ""
            return
        if kind == "translation":
            self.translation = event.get("text") or ""
            self.notice = ""
            return
        if kind == "error":
            self.notice = event.get("message") or "连接中断"

    def big_text(self) -> str:
        if self.notice:
            return self.notice
        if self.translation:
            return self.translation
        if not self.source:
            return "等待字幕"
        return ""
