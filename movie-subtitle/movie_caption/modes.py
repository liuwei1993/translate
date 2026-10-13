"""电影字幕只用网页网关已经实现的中日方向。"""

TARGETS = ("ja-auto", "ja", "ja2zh")
LABELS = {
    "ja-auto": "中日互译",
    "ja": "中文 → 日文",
    "ja2zh": "日文 → 中文",
}
DEFAULT_TARGET = "ja-auto"
