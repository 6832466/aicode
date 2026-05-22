import logging
import sys
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QTextCursor, QColor, QTextCharFormat
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout
from qfluentwidgets import PushButton, BodyLabel, CardWidget

MAX_LOG_LINES = 2000
REDRAW_INTERVAL_MS = 200

LEVEL_COLORS = {
    "ERROR": "#FF5252",
    "CRITICAL": "#FF1744",
    "WARNING": "#FFAB40",
    "INFO": "#B0BEC5",
    "DEBUG": "#78909C",
}


class LogSignal(QObject):
    message_received = Signal(str, str)


class QtLogHandler(logging.Handler):
    def __init__(self, signal: LogSignal):
        super().__init__()
        self._signal = signal

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        self._signal.message_received.emit(record.levelname, msg)


class LogWidget(CardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logWidget")

        self._entries: list[tuple[str, str, str]] = []
        self._pending: list[tuple[str, str, str]] = []
        self._batch_timer = QTimer(self)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.setInterval(REDRAW_INTERVAL_MS)
        self._batch_timer.timeout.connect(self._redraw)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = BodyLabel("运行日志")
        header.addWidget(title)
        header.addStretch()

        self._btn_clear = PushButton("清空")
        self._btn_clear.setFixedWidth(60)
        self._btn_clear.clicked.connect(self.clear)
        header.addWidget(self._btn_clear)
        layout.addLayout(header)

        from PySide6.QtWidgets import QTextEdit
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._text.setStyleSheet(
            "QTextEdit { background-color: #1E1E2E; color: #CDD6F4; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; "
            "border: 1px solid #313244; border-radius: 4px; padding: 6px; }"
        )
        layout.addWidget(self._text)

    def append(self, level: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = (ts, level, message)
        self._entries.insert(0, entry)
        self._pending.append(entry)

        while len(self._entries) > MAX_LOG_LINES:
            self._entries.pop()

        if not self._batch_timer.isActive():
            self._batch_timer.start()

    def info(self, message: str):
        self.append("INFO", message)

    def warning(self, message: str):
        self.append("WARNING", message)

    def error(self, message: str):
        self.append("ERROR", message)

    def clear(self):
        self._entries.clear()
        self._pending.clear()
        self._text.clear()

    def _redraw(self):
        if not self._pending:
            return

        pending = self._pending
        self._pending = []

        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.Start)

        for ts, level, msg in pending:
            color = LEVEL_COLORS.get(level, "#B0BEC5")

            fmt_ts = QTextCharFormat()
            fmt_ts.setForeground(QColor("#6C7086"))
            fmt_level = QTextCharFormat()
            fmt_level.setForeground(QColor(color))
            fmt_level.setFontWeight(700)
            fmt_msg = QTextCharFormat()
            fmt_msg.setForeground(QColor("#CDD6F4"))

            cursor.insertText(f"[{ts}] ", fmt_ts)
            cursor.insertText(f"[{level}] ", fmt_level)
            cursor.insertText(f"{msg}\n", fmt_msg)

        if self._text.document().blockCount() > MAX_LOG_LINES:
            self._rebuild_full_text()
        else:
            self._text.verticalScrollBar().setValue(0)

    def _rebuild_full_text(self):
        self._text.clear()
        cursor = self._text.textCursor()

        for ts, level, msg in self._entries:
            color = LEVEL_COLORS.get(level, "#B0BEC5")
            fmt_ts = QTextCharFormat()
            fmt_ts.setForeground(QColor("#6C7086"))
            fmt_level = QTextCharFormat()
            fmt_level.setForeground(QColor(color))
            fmt_level.setFontWeight(700)
            fmt_msg = QTextCharFormat()
            fmt_msg.setForeground(QColor("#CDD6F4"))

            cursor.insertText(f"[{ts}] ", fmt_ts)
            cursor.insertText(f"[{level}] ", fmt_level)
            cursor.insertText(f"{msg}\n", fmt_msg)

        self._text.verticalScrollBar().setValue(0)


def setup_app_logging(log_widget: LogWidget) -> LogSignal:
    """Configure Python logging to forward to the log widget."""
    signal = LogSignal()

    handler = QtLogHandler(signal)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)

    for noisy in ("asyncio", "aiohttp", "urllib3", "chardet", "PIL", "qfluentwidgets", "openai", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    signal.message_received.connect(log_widget.append)

    _old_hook = sys.excepthook

    def _qt_excepthook(exc_type, exc_value, exc_tb):
        import traceback
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        log_widget.error("".join(tb_lines).rstrip())
        if _old_hook:
            _old_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _qt_excepthook
    log_widget.info("日志系统已初始化")
    return signal