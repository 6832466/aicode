"""日志页面 —— 浅色调，最新日志在上方。"""

import html as _html
from datetime import datetime

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PySide6.QtGui import QFont, QTextCursor

from log_service import log_service

LIGHT_COLORS = {
    "error": "#d32f2f",
    "warning": "#e65100",
    "info": "#616161",
    "success": "#2e7d32",
}

MAX_LINES = 500


class LogPage(QWidget):
    """独立的日志页面，订阅全局 LogService 信号。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("logPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self._edit = QTextEdit()
        self._edit.setReadOnly(True)
        self._edit.setPlaceholderText("运行日志…")
        self._edit.setFont(QFont("Consolas", 10))
        self._edit.setStyleSheet("""
            QTextEdit {
                background: #ffffff;
                color: #212121;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        layout.addWidget(self._edit)

        log_service.log_message.connect(self._on_log)
        self.destroyed.connect(
            lambda: log_service.log_message.disconnect(self._on_log)
        )

    def _on_log(self, message: str, level: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        color = LIGHT_COLORS.get(level, "#616161")
        escaped = _html.escape(message)
        line = (
            f'<span style="color:{color};font-weight:bold">[{ts}]</span>'
            f'<span style="color:{color}"> [{level.upper()}]</span>'
            f' {escaped}'
        )
        cursor = self._edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.insertHtml(line + "<br>")
        # 超过上限时删除末尾最旧日志
        if self._edit.document().blockCount() > MAX_LINES:
            last_block = self._edit.document().lastBlock()
            cursor = QTextCursor(last_block)
            cursor.movePosition(
                QTextCursor.MoveOperation.End,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
