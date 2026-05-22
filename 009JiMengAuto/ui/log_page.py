"""日志页面 - 即梦日志查看器"""

import logging
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QAbstractItemView,
)
from qfluentwidgets import (
    CardWidget, PushButton, FluentIcon, ComboBox,
    BodyLabel, StrongBodyLabel, ScrollArea, InfoBar,
)

from ui.widgets import LogLine
from utils.theme import THEME


class LogPage(QWidget):
    """日志页面"""

    MAX_LOG_LINES = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logs: list[tuple[str, str, str]] = []  # (time, level, message)
        self._paused = False

        self._init_ui()
        self._setup_log_handler()
        self._start_timer()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # 级别筛选
        toolbar.addWidget(BodyLabel("日志级别:"))
        self._level_combo = ComboBox()
        self._level_combo.addItems(["全部", "INFO", "WARN", "ERROR"])
        self._level_combo.setCurrentIndex(0)
        self._level_combo.setFixedWidth(100)
        toolbar.addWidget(self._level_combo)

        self._btn_pause = PushButton(FluentIcon.PAUSE, "暂停")
        self._btn_clear = PushButton(FluentIcon.DELETE, "清空")
        self._btn_export = PushButton(FluentIcon.SAVE, "导出")

        toolbar.addWidget(self._btn_pause)
        toolbar.addWidget(self._btn_clear)
        toolbar.addWidget(self._btn_export)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── 日志区域 ──
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)

        self._log_container = QWidget()
        self._log_container.setAttribute(Qt.WA_StyledBackground)
        self._log_layout = QVBoxLayout(self._log_container)
        self._log_layout.setContentsMargins(0, 0, 0, 0)
        self._log_layout.setSpacing(2)
        self._log_layout.addStretch()

        scroll.setWidget(self._log_container)
        layout.addWidget(scroll)

        # 连接信号
        self._level_combo.currentTextChanged.connect(self._on_filter)
        self._btn_pause.clicked.connect(self._on_pause)
        self._btn_clear.clicked.connect(self._on_clear)
        self._btn_export.clicked.connect(self._on_export)

    def _setup_log_handler(self):
        """设置日志处理器"""
        self._log_handler = LogHandler(self)
        logging.getLogger().addHandler(self._log_handler)

    def _start_timer(self):
        """启动刷新定时器"""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_logs)
        self._timer.start(500)  # 每500ms刷新

    def add_log(self, level: str, message: str):
        """添加日志"""
        if self._paused:
            return
        time = datetime.now().strftime("%H:%M:%S")
        self._logs.append((time, level, message))
        # 限制最大条数
        if len(self._logs) > self.MAX_LOG_LINES:
            self._logs = self._logs[-self.MAX_LOG_LINES:]

    def _refresh_logs(self):
        """刷新日志显示"""
        if self._paused:
            return
        # 清空并重建
        self._clear_log_widgets()
        filter_level = self._level_combo.currentText()
        for time, level, message in self._logs:
            if filter_level != "全部" and level != filter_level:
                continue
            self._add_log_widget(time, level, message)
        # 滚动到底部
        self._log_container.layout().update()

    def _clear_log_widgets(self):
        """清空日志控件"""
        while self._log_layout.count() > 1:  # 保留最后的 stretch
            item = self._log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_log_widget(self, time: str, level: str, message: str):
        """添加日志控件"""
        line = LogLine(time, level, message)
        self._log_layout.insertWidget(self._log_layout.count() - 1, line)

    def _on_filter(self, level: str):
        """筛选变化"""
        self._refresh_logs()

    def _on_pause(self):
        """暂停/继续"""
        self._paused = not self._paused
        self._btn_pause.setText("继续" if self._paused else "暂停")
        self._btn_pause.setIcon(FluentIcon.PLAY if self._paused else FluentIcon.PAUSE)

    def _on_clear(self):
        """清空日志"""
        self._logs.clear()
        self._clear_log_widgets()
        InfoBar.success("已清空", "日志已清空", parent=self, duration=2000)

    def _on_export(self):
        """导出日志"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "", "文本文件 (*.txt)"
        )
        if not path:
            return
        try:
            from pathlib import Path
            lines = [f"[{t}] [{l}] {m}" for t, l, m in self._logs]
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            InfoBar.success("导出成功", f"日志已导出到 {path}", parent=self, duration=3000)
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self, duration=3000)


class LogHandler(logging.Handler):
    """自定义日志处理器"""

    def __init__(self, page: LogPage):
        super().__init__()
        self._page = page

    def emit(self, record: logging.LogRecord):
        """处理日志记录"""
        level = record.levelname
        if level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            display_level = {"WARNING": "WARN", "CRITICAL": "ERROR"}.get(level, level)
            self._page.add_log(display_level, record.getMessage())
