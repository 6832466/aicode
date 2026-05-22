"""选集按钮 - 可多选的方格按钮"""
from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt


class EpisodeButton(QPushButton):
    """单个剧集选择按钮, 52x40 可多选"""

    def __init__(self, number: int, parent=None):
        super().__init__(str(number), parent)
        self._number = number
        self._status = "pending"  # pending, ready, downloading, done

        self.setCheckable(True)
        self.setAutoExclusive(False)
        self.setFixedSize(52, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(QFont("Microsoft YaHei", 11))
        self.toggled.connect(lambda _: self._apply_style())
        self._apply_style()

    @property
    def number(self) -> int:
        return self._number

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str):
        self._status = value
        self._apply_style()

    def _apply_style(self):
        if self._status == "done":
            bg = "#e8f5e9"
            color = "#2e7d32"
            border = "#81c784"
            hover_bg = "#c8e6c9"
        elif self._status == "downloading":
            bg = "#e3f2fd"
            color = "#1565c0"
            border = "#64b5f6"
            hover_bg = "#bbdefb"
        elif self.isChecked():
            bg = "#0078d4"
            color = "#ffffff"
            border = "#005a9e"
            hover_bg = "#1084d8"
        else:
            bg = "#fafafa"
            color = "#444444"
            border = "#d0d0d0"
            hover_bg = "#e3f2fd"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                border: 2px solid {border};
                border-radius: 8px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: #0078d4;
                background-color: {hover_bg};
            }}
            QPushButton:pressed {{
                border-color: #005a9e;
            }}
        """)
