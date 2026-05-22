import logging
import sys
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
)
from PySide6.QtGui import QTextCursor, QColor, QTextCharFormat
from qfluentwidgets import PushButton, BodyLabel, CardWidget, FluentIcon

MAX_LOG_LINES = 2000
REDRAW_INTERVAL_MS = 200  # batch redraws at most every 200ms

LEVEL_COLORS = {
    "ERROR": "#FF5252",
    "CRITICAL": "#FF1744",
    "WARNING": "#FFAB40",
    "INFO": "#B0BEC5",
    "DEBUG": "#78909C",
}


class LogSignal(QObject):
    """Bridge Python logging → Qt signal (thread-safe)."""
    message_received = Signal(str, str)  # level, text


class QtLogHandler(logging.Handler):
    """logging.Handler that emits Qt signals."""

    def __init__(self, signal: LogSignal):
        super().__init__()
        self._signal = signal

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        self._signal.message_received.emit(record.levelname, msg)


class LogWidget(CardWidget):
    """Scrollable log viewer — newest entries at top, color-coded.

    Uses a batch timer to avoid redrawing on every single log message,
    which would freeze the UI under high-frequency logging.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logWidget")

        self._entries: list[tuple[str, str, str]] = []  # (timestamp, level, text)
        self._pending: list[tuple[str, str, str]] = []   # not yet rendered
        self._batch_timer = QTimer(self)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.setInterval(200)
        self._batch_timer.timeout.connect(self._redraw)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title = BodyLabel("运行日志")
        header.addWidget(title)
        header.addStretch()

        self._btn_clear = PushButton("清空")
        self._btn_clear.setFixedWidth(60)
        self._btn_clear.clicked.connect(self.clear)

        header.addWidget(self._btn_clear)
        layout.addLayout(header)

        # Text area
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._text.setStyleSheet(
            "QTextEdit { background-color: #1E1E2E; color: #CDD6F4; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; "
            "border: 1px solid #313244; border-radius: 4px; padding: 6px; }"
        )
        layout.addWidget(self._text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, level: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = (ts, level, message)

        self._entries.insert(0, entry)
        self._pending.append(entry)

        # Trim old entries
        while len(self._entries) > MAX_LOG_LINES:
            self._entries.pop()

        # Batch: start timer if not already running
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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

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
            ts_line = f"[{ts}] "

            fmt_level = QTextCharFormat()
            fmt_level.setForeground(QColor(color))
            fmt_level.setFontWeight(700)
            level_line = f"[{level}] "

            fmt_msg = QTextCharFormat()
            fmt_msg.setForeground(QColor("#CDD6F4"))
            msg_line = f"{msg}\n"

            cursor.insertText(ts_line, fmt_ts)
            cursor.insertText(level_line, fmt_level)
            cursor.insertText(msg_line, fmt_msg)

        # Trim text buffer if it's grown too large (avoid unbounded growth)
        max_text_lines = MAX_LOG_LINES
        if self._text.document().blockCount() > max_text_lines:
            self._rebuild_full_text()
        else:
            self._text.verticalScrollBar().setValue(0)

    def _rebuild_full_text(self):
        """Rebuild entire text content from _entries (only called when trimming)."""
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
    handler.setLevel(logging.INFO)  # block ALL debug — UI should never show DEBUG

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)    # logger tree can still produce debug (for file output, etc.)
    root.addHandler(handler)

    # Suppress noisy INFO as well — these libraries chat at INFO level too
    for noisy in ("asyncio", "aiohttp", "urllib3", "chardet", "PIL", "qfluentwidgets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Connect signal to widget
    signal.message_received.connect(log_widget.append)

    # Also capture unhandled exceptions via sys.excepthook
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
