"""日志页面 — 实时查看应用日志"""
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QComboBox, QPushButton, QFileDialog,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from qfluentwidgets import CardWidget, FluentIcon as FIF

from app.utils.logger import get_logger

_log = get_logger('LogsPage')


class LogsPage(QWidget):
    """日志查看页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background: #FFFFFF;')
        self._log_dir = self._find_log_dir()
        self._auto_scroll = True
        self._current_file = ""
        self._setup_ui()
        self._load_logs()
        self._refresh_file_list()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(3000)

    def _find_log_dir(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel('应用日志')
        title.setFont(QFont('Microsoft YaHei', 16, QFont.Bold))
        title.setStyleSheet('color: #1a1a1a; border: none;')
        layout.addWidget(title)

        # 工具栏
        toolbar_card = CardWidget()
        toolbar_card.setStyleSheet('CardWidget { background: #FAFBFC; border-radius: 10px; }')
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(16, 10, 16, 10)
        toolbar_layout.setSpacing(10)

        self._file_combo = QComboBox()
        self._file_combo.setMinimumWidth(200)
        self._file_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #D0D7DE; border-radius: 6px;
                padding: 5px 10px; font-size: 13px; background: #FFFFFF;
            }
            QComboBox:hover { border-color: #0078D4; }
            QComboBox::drop-down { border: none; width: 24px; }
        """)
        self._file_combo.currentTextChanged.connect(self._on_file_changed)
        toolbar_layout.addWidget(QLabel('日志文件:'))
        toolbar_layout.addWidget(self._file_combo, stretch=1)

        open_btn = QPushButton('打开日志目录')
        open_btn.setStyleSheet(self._btn_style())
        open_btn.clicked.connect(self._open_log_dir)
        toolbar_layout.addWidget(open_btn)

        self._auto_scroll_btn = QPushButton('自动滚动: 开')
        self._auto_scroll_btn.setStyleSheet(self._btn_style())
        self._auto_scroll_btn.clicked.connect(self._toggle_auto_scroll)
        toolbar_layout.addWidget(self._auto_scroll_btn)

        clear_btn = QPushButton('清空显示')
        clear_btn.setStyleSheet(self._btn_style('#E02020'))
        clear_btn.clicked.connect(lambda: self._log_view.clear())
        toolbar_layout.addWidget(clear_btn)

        layout.addWidget(toolbar_card)

        # 日志内容
        log_card = CardWidget()
        log_card.setStyleSheet('CardWidget { background: #1E1E1E; border-radius: 10px; }')
        log_inner = QVBoxLayout(log_card)
        log_inner.setContentsMargins(8, 8, 8, 8)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont('Cascadia Code', 10))
        self._log_view.setStyleSheet("""
            QTextEdit {
                background: #1E1E1E;
                color: #D4D4D4;
                border: none;
                padding: 8px;
                selection-background-color: #264F78;
            }
            QScrollBar:vertical {
                background: #2D2D2D;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        log_inner.addWidget(self._log_view)

        layout.addWidget(log_card, stretch=1)

        # 底部状态
        status_bar = QHBoxLayout()
        self._status_label = QLabel('')
        self._status_label.setStyleSheet('color: #888; font-size: 12px; border: none;')
        status_bar.addWidget(self._status_label)
        status_bar.addStretch()
        layout.addLayout(status_bar)

    def _btn_style(self, accent: str = '#0078D4') -> str:
        return f"""
            QPushButton {{
                background: #F0F2F5; border: 1px solid #D0D7DE;
                border-radius: 6px; padding: 5px 14px;
                font-size: 13px; color: #333;
            }}
            QPushButton:hover {{
                background: #E8F0FE; border-color: {accent}; color: {accent};
            }}
        """

    def _refresh_file_list(self):
        current = self._file_combo.currentText()
        self._file_combo.blockSignals(True)
        self._file_combo.clear()
        if os.path.isdir(self._log_dir):
            files = sorted(
                [f for f in os.listdir(self._log_dir) if f.endswith('.log')],
                reverse=True
            )
            self._file_combo.addItems(files)
        idx = self._file_combo.findText(current)
        if idx >= 0:
            self._file_combo.setCurrentIndex(idx)
        self._file_combo.blockSignals(False)

    def _on_file_changed(self, filename: str):
        if not filename:
            return
        self._current_file = os.path.join(self._log_dir, filename)
        self._load_logs()

    def _load_logs(self):
        try:
            files = [os.path.join(self._log_dir, f) for f in os.listdir(self._log_dir) if f.endswith('.log')]
            if not files:
                self._log_view.setPlainText("暂无日志文件")
                return
            # 默认选最新的文件
            latest = max(files, key=os.path.getmtime)
            filename = os.path.basename(latest)
            if not self._current_file:
                self._current_file = latest
                idx = self._file_combo.findText(filename)
                if idx >= 0:
                    self._file_combo.blockSignals(True)
                    self._file_combo.setCurrentIndex(idx)
                    self._file_combo.blockSignals(False)
            self._read_and_display()
        except Exception as e:
            _log.exception(f'加载日志失败: {e}')

    def _read_and_display(self):
        if not self._current_file or not os.path.exists(self._current_file):
            self._log_view.setPlainText("日志文件不存在")
            return
        try:
            with open(self._current_file, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            scrollbar = self._log_view.verticalScrollBar()
            was_at_end = scrollbar.value() >= scrollbar.maximum() - 10

            self._log_view.setPlainText(content)

            if was_at_end or self._auto_scroll:
                cursor = self._log_view.textCursor()
                cursor.movePosition(QTextCursor.End)
                self._log_view.setTextCursor(cursor)

            size_kb = os.path.getsize(self._current_file) / 1024
            self._status_label.setText(
                f"文件: {os.path.basename(self._current_file)}  |  "
                f"大小: {size_kb:.1f} KB  |  自动刷新: 3秒"
            )
        except Exception as e:
            _log.exception(f'读取日志失败: {e}')

    def _toggle_auto_scroll(self):
        self._auto_scroll = not self._auto_scroll
        state = '开' if self._auto_scroll else '关'
        self._auto_scroll_btn.setText(f'自动滚动: {state}')

    def _open_log_dir(self):
        abs_path = os.path.abspath(self._log_dir)
        os.makedirs(abs_path, exist_ok=True)
        os.startfile(abs_path)

    def _refresh(self):
        self._refresh_file_list()
        if self._current_file:
            self._read_and_display()

    def refresh(self):
        self._refresh()
