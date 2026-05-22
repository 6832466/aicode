"""日志页面 - 实时彩色日志 (最新置顶)"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QFileDialog
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor, QColor
from qfluentwidgets import BodyLabel, TransparentPushButton, FluentIcon


class LogsPage(QWidget):
    log_received = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._log_lines: list[tuple[str, str]] = []  # [(message, level), ...]
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)

        # 工具栏
        toolbar = QHBoxLayout()
        title = BodyLabel("实时日志")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self._pause_btn = TransparentPushButton(FluentIcon.PAUSE, "暂停滚动")
        self._pause_btn.clicked.connect(self._toggle_pause)
        toolbar.addWidget(self._pause_btn)

        clear_btn = TransparentPushButton(FluentIcon.DELETE, "清空")
        clear_btn.clicked.connect(self.clear_logs)
        toolbar.addWidget(clear_btn)

        export_btn = TransparentPushButton(FluentIcon.SAVE_AS, "导出")
        export_btn.clicked.connect(self._export_logs)
        toolbar.addWidget(export_btn)

        layout.addLayout(toolbar)

        # 日志文本框
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFont("Consolas", 11))
        self._text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        layout.addWidget(self._text_edit)

    def append_log(self, message: str, level: str):
        """添加一条日志 (线程安全, 通过 Signal 调用)"""
        self._log_lines.append((message, level))
        if not self._paused:
            self._render_logs()

    def _render_logs(self):
        """重新渲染日志 (最新置顶)"""
        try:
            self._text_edit.clear()
            colors = {
                "INFO": "#cccccc",
                "SUCCESS": "#4ec9b0",
                "WARNING": "#ce9178",
                "ERROR": "#f14c4c",
                "DEBUG": "#808080",
            }

            for message, level in reversed(self._log_lines):
                color = colors.get(level, "#cccccc")
                escaped = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                self._text_edit.append(
                    f'<span style="color:{color};">{escaped}</span>'
                )
        except Exception:
            pass  # 渲染失败不阻塞日志接收

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._pause_btn.setText("继续滚动")
            self._pause_btn.setIcon(FluentIcon.PLAY)
        else:
            self._pause_btn.setText("暂停滚动")
            self._pause_btn.setIcon(FluentIcon.PAUSE)
            self._render_logs()

    def clear_logs(self):
        self._log_lines.clear()
        self._text_edit.clear()

    def _export_logs(self):
        import logging
        _logger = logging.getLogger("hongguo")
        try:
            path, _ = QFileDialog.getSaveFileName(
                self, "导出日志", "hongguo_logs.txt", "Text Files (*.txt *.log)"
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    for message, level in reversed(self._log_lines):
                        f.write(f"[{level}] {message}\n")
        except OSError:
            _logger.exception("导出日志失败")
