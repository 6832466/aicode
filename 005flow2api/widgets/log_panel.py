"""Bottom log panel showing generation progress and messages."""
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QLabel
from qfluentwidgets import CardWidget


class LogPanel(CardWidget):
    """Bottom panel displaying a scrollable log of generation events."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        header = QLabel("生成日志")
        header.setStyleSheet("font-weight: bold; color: #555; font-size: 12px;")
        layout.addWidget(header)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #ccc; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 11px; "
            "border: 1px solid #333; border-radius: 4px; }"
        )
        self.log_view.document().setMaximumBlockCount(500)
        layout.addWidget(self.log_view)

    def log(self, message: str, level: str = "INFO"):
        """Append a timestamped message to the log."""
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {
            "INFO": "#ccc",
            "SUCCESS": "#5cb85c",
            "WARN": "#f0ad4e",
            "ERROR": "#d9534f",
        }
        color = colors.get(level, "#ccc")
        self.log_view.append(
            f'<span style="color:#888;">[{ts}]</span> '
            f'<span style="color:{color};">[{level}]</span> {message}'
        )

    def clear(self):
        """Clear all log entries."""
        self.log_view.clear()
