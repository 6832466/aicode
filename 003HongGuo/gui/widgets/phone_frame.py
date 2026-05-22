"""手机框 — 9:16 比例容器, 内含 QWebEngineView"""
from PySide6.QtWidgets import QFrame, QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtWebEngineWidgets import QWebEngineView


class PhoneFrame(QFrame):
    """仿手机屏幕的 9:16 容器"""

    def __init__(self, web_view: QWebEngineView, parent=None):
        super().__init__(parent)
        self._web_view = web_view
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.addWidget(self._web_view)

        self.setStyleSheet("""
            PhoneFrame {
                background: #1a1a1a;
                border-radius: 20px;
                border: 3px solid #333;
            }
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def heightForWidth(self, w: int) -> int:
        return int((w - 16) * 16.0 / 9.0 + 24)

    def hasHeightForWidth(self) -> bool:
        return True
