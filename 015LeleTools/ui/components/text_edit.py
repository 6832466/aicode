"""
增强版文本编辑区 — 字数统计 + 工具栏
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLabel,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QTextCursor
from qfluentwidgets import PushButton, CaptionLabel


def count_chinese_chars(text: str) -> int:
    """统计中文字符数（含中文标点）"""
    count = 0
    for ch in text:
        if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯':
            count += 1
        elif ch.isdigit():
            count += 1
    return count


class TextEditWidget(QWidget):
    """带字数统计和工具栏的文本编辑器"""

    textChanged = Signal()

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._init_ui(placeholder)

    def _init_ui(self, placeholder: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.count_label = CaptionLabel("字数: 0")
        toolbar.addWidget(self.count_label)

        toolbar.addStretch()

        self.btn_copy = PushButton("复制")
        toolbar.addWidget(self.btn_copy)

        self.btn_clear = PushButton("清空")
        toolbar.addWidget(self.btn_clear)

        self.btn_format = PushButton("格式化")
        toolbar.addWidget(self.btn_format)

        layout.addLayout(toolbar)

        # 编辑区
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(placeholder)
        self.editor.setFont(QFont("Microsoft YaHei", 11))
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor, 1)

    def _on_text_changed(self):
        text = self.editor.toPlainText()
        count = count_chinese_chars(text)
        self.count_label.setText(f"字数: {count}")
        self.textChanged.emit()

    def text(self) -> str:
        return self.editor.toPlainText()

    def setText(self, text: str):
        self.editor.setPlainText(text)

    def clear(self):
        self.editor.clear()

    def selectedText(self) -> str:
        cursor = self.editor.textCursor()
        return cursor.selectedText()

    def appendText(self, text: str):
        """追加文本（用于流式输出）"""
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.editor.insertPlainText(text)
