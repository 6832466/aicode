from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QApplication
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QFont
from qfluentwidgets import (
    PushButton, LineEdit, BodyLabel, FluentIcon, SubtitleLabel,
    ComboBox, ToolButton, isDarkTheme
)
import logging


# Light theme colors
_LEVEL_COLORS_LIGHT = {
    "DEBUG":    "#757575",
    "INFO":     "#1a1a1a",
    "WARNING":  "#e65100",
    "ERROR":    "#b71c1c",
    "CRITICAL": "#880000",
}
_LEVEL_BG_LIGHT = {
    "ERROR":    "#ffebee",
    "CRITICAL": "#fce4ec",
    "WARNING":  "#fff8e1",
}

# Dark theme colors
_LEVEL_COLORS_DARK = {
    "DEBUG":    "#9E9E9E",
    "INFO":     "#E0E0E0",
    "WARNING":  "#FFB74D",
    "ERROR":    "#EF5350",
    "CRITICAL": "#FF1744",
}
_LEVEL_BG_DARK = {
    "ERROR":    "#3E1A1A",
    "CRITICAL": "#4A0000",
    "WARNING":  "#3E2E00",
}


def _level_colors():
    return _LEVEL_COLORS_DARK if isDarkTheme() else _LEVEL_COLORS_LIGHT


def _level_bg():
    return _LEVEL_BG_DARK if isDarkTheme() else _LEVEL_BG_LIGHT


class LogSignalBridge(QObject):
    """Thread-safe bridge: emits log records to the UI thread."""
    record_emitted = Signal(str, str, str)  # level, time, message


_bridge = LogSignalBridge()


class _QtHandler(logging.Handler):
    def emit(self, record):
        try:
            level = record.levelname
            time_str = self.formatter.formatTime(record, "%H:%M:%S") if self.formatter else ""
            msg = record.getMessage()
            if record.exc_info:
                import traceback
                msg += "\n" + "".join(traceback.format_exception(*record.exc_info))
            _bridge.record_emitted.emit(level, time_str, msg)
        except Exception:
            pass


def install_log_handler():
    """Install the Qt log handler once at startup."""
    fmt = logging.Formatter("%(asctime)s")
    fmt.datefmt = "%H:%M:%S"
    handler = _QtHandler()
    handler.setFormatter(fmt)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    return handler


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_records: list[tuple[str, str, str]] = []  # (level, time, msg)
        self._filter_level = "ALL"
        self._filter_text = ""
        self._build_ui()
        _bridge.record_emitted.connect(self._on_record)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # title row
        title_row = QHBoxLayout()
        title_row.addWidget(SubtitleLabel("实时运行日志"))
        title_row.addStretch()
        layout.addLayout(title_row)

        # toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(BodyLabel("级别："))
        self.level_combo = ComboBox()
        for lvl in ("ALL", "DEBUG", "INFO", "WARNING", "ERROR"):
            self.level_combo.addItem(lvl)
        self.level_combo.setFixedWidth(100)
        self.level_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.level_combo)

        toolbar.addWidget(BodyLabel("搜索："))
        self.search_edit = LineEdit()
        self.search_edit.setPlaceholderText("输入关键词过滤...")
        self.search_edit.setFixedWidth(200)
        self.search_edit.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.search_edit)

        toolbar.addStretch()

        copy_btn = PushButton(FluentIcon.COPY, "复制全部")
        copy_btn.clicked.connect(self._copy_all)
        clear_btn = PushButton(FluentIcon.DELETE, "清空")
        clear_btn.clicked.connect(self._clear)
        toolbar.addWidget(copy_btn)
        toolbar.addWidget(clear_btn)
        layout.addLayout(toolbar)

        # log view
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 12))
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.log_view, 1)

        # count label
        self.count_label = BodyLabel("共 0 条")
        layout.addWidget(self.count_label)

    def _on_record(self, level: str, time_str: str, msg: str):
        self._all_records.append((level, time_str, msg))
        if self._matches(level, msg):
            self._append_to_view(level, time_str, msg)
        self.count_label.setText(f"共 {len(self._all_records)} 条")

    def _matches(self, level: str, msg: str) -> bool:
        if self._filter_level != "ALL":
            order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if order.index(level) < order.index(self._filter_level):
                return False
        if self._filter_text and self._filter_text.lower() not in msg.lower():
            return False
        return True

    def _append_to_view(self, level: str, time_str: str, msg: str):
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = QTextCharFormat()
        color = _level_colors().get(level, _level_colors()["INFO"])
        fmt.setForeground(QColor(color))
        bg = _level_bg()
        if level in bg:
            fmt.setBackground(QColor(bg[level]))

        prefix = f"[{time_str}] [{level:<8}] "
        cursor.insertText(prefix + msg + "\n", fmt)

        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_filter_changed(self):
        self._filter_level = self.level_combo.currentText()
        self._filter_text = self.search_edit.text()
        self._rebuild_view()

    def _rebuild_view(self):
        self.log_view.clear()
        for level, time_str, msg in self._all_records:
            if self._matches(level, msg):
                self._append_to_view(level, time_str, msg)

    def _copy_all(self):
        lines = []
        for level, time_str, msg in self._all_records:
            if self._matches(level, msg):
                lines.append(f"[{time_str}] [{level}] {msg}")
        QApplication.clipboard().setText("\n".join(lines))

    def _clear(self):
        self._all_records.clear()
        self.log_view.clear()
        self.count_label.setText("共 0 条")
