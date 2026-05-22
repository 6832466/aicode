import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
)
from qfluentwidgets import BodyLabel, LineEdit

logger = logging.getLogger(__name__)


class PrefixSuffixWidget(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("提示词前缀 / 后缀", parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        prefix_row = QHBoxLayout()
        prefix_label = BodyLabel("前缀:")
        prefix_label.setFixedWidth(55)
        self._prefix_edit = LineEdit(self)
        self._prefix_edit.setPlaceholderText("加在所有提示词前面，如 '电影质感, 8k, '")
        prefix_row.addWidget(prefix_label)
        prefix_row.addWidget(self._prefix_edit)
        layout.addLayout(prefix_row)

        suffix_row = QHBoxLayout()
        suffix_label = BodyLabel("后缀:")
        suffix_label.setFixedWidth(55)
        self._suffix_edit = LineEdit(self)
        self._suffix_edit.setPlaceholderText("加在所有提示词后面，如 ', 清晰对焦, 胶片颗粒感'")
        suffix_row.addWidget(suffix_label)
        suffix_row.addWidget(self._suffix_edit)
        layout.addLayout(suffix_row)

        hint = BodyLabel("前后缀会自动用空格与原始提示词拼接。")
        hint.setStyleSheet("color: #888;")
        layout.addWidget(hint)

    @property
    def prefix(self) -> str:
        try:
            return self._prefix_edit.text().strip()
        except Exception:
            logger.exception("读取前缀失败")
            return ""

    @property
    def suffix(self) -> str:
        try:
            return self._suffix_edit.text().strip()
        except Exception:
            logger.exception("读取后缀失败")
            return ""

    def set_prefix(self, text: str):
        try:
            self._prefix_edit.setText(text or "")
        except Exception:
            logger.exception("设置前缀失败")

    def set_suffix(self, text: str):
        try:
            self._suffix_edit.setText(text or "")
        except Exception:
            logger.exception("设置后缀失败")
