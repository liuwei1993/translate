"""Linux 和 Windows 共用的置顶字幕窗。"""

import json

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from movie_caption.client import Target, parse_event
from movie_caption.lines import CaptionLines
from movie_caption.modes import LABELS, TARGETS

_TEXT_FLAGS = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap


def caption_font(pixel_size: int) -> QFont:
    font = QFont()
    font.setFamilies(
        [
            "Noto Sans CJK JP",
            "Noto Sans CJK",
            "Yu Gothic",
            "Meiryo",
            "Microsoft YaHei",
            "Segoe UI",
        ]
    )
    font.setPixelSize(pixel_size)
    font.setWeight(QFont.Weight.DemiBold)
    return font


class CaptionWindow(QWidget):
    incoming = Signal(str)

    def __init__(self, target: Target, on_close=None) -> None:
        super().__init__()
        self.target = target
        self.lines = CaptionLines()
        self._on_close = on_close
        self._drag = None
        self._user_moved = False
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowTitle("电影字幕")
        self.incoming.connect(self._apply)
        self._relayout()

    def post(self, event: dict) -> None:
        self.incoming.emit(json.dumps(event, ensure_ascii=False))

    def choose(self, target: str) -> None:
        if target not in TARGETS:
            raise ValueError(target)
        self.target.value = target
        self.lines = CaptionLines()
        self._relayout()
        self.update()

    def _apply(self, payload: str) -> None:
        event = parse_event(payload)
        if event is None:
            return
        self.lines.apply(event)
        self._relayout()
        self.update()

    def _relayout(self) -> None:
        source_font = caption_font(22)
        big_font = caption_font(40)
        screen = self.screen() or QApplication.primaryScreen()
        max_width = int(screen.availableGeometry().width() * 0.8) if screen is not None else 960
        source_rect = QFontMetrics(source_font).boundingRect(
            0, 0, max_width - 32, 400, _TEXT_FLAGS, self.lines.source or " "
        )
        big_rect = QFontMetrics(big_font).boundingRect(
            0, 0, max_width - 32, 400, _TEXT_FLAGS, self.lines.big_text() or " "
        )
        width = min(max(source_rect.width(), big_rect.width(), 240) + 32, max_width)
        height = max(source_rect.height(), 28) + max(big_rect.height(), 48) + 28
        self.resize(width, height)
        if self._user_moved or screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.x() + (geo.width() - width) // 2, geo.bottom() - height - 48)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        source_font = caption_font(22)
        source_height = QFontMetrics(source_font).boundingRect(
            0, 0, width - 32, 400, _TEXT_FLAGS, self.lines.source or " "
        ).height()
        self._draw(painter, source_font, QRect(16, 8, width - 32, source_height), self.lines.source)
        big_top = 12 + source_height
        self._draw(
            painter,
            caption_font(40),
            QRect(16, big_top, width - 32, self.height() - big_top - 8),
            self.lines.big_text(),
        )

    def _draw(self, painter: QPainter, font: QFont, rect: QRect, text: str) -> None:
        if not text:
            return
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0))
        for dx in (-2, 0, 2):
            for dy in (-2, 0, 2):
                if dx == 0 and dy == 0:
                    continue
                painter.drawText(rect.translated(dx, dy), _TEXT_FLAGS, text)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(rect, _TEXT_FLAGS, text)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            self._user_moved = True

    def mouseReleaseEvent(self, _event) -> None:
        self._drag = None

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        for key in TARGETS:
            action = menu.addAction(LABELS[key])
            action.setCheckable(True)
            action.setChecked(key == self.target.value)
            action.triggered.connect(lambda _checked=False, key=key: self.choose(key))
        menu.addSeparator()
        menu.addAction("退出").triggered.connect(self.close)
        menu.exec(event.globalPos())

    def closeEvent(self, event) -> None:
        if self._on_close is not None:
            self._on_close()
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()
