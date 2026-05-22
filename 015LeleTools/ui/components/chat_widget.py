"""
多轮对话组件 — 消息气泡列表 + 输入区
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QTextEdit, QFrame,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from qfluentwidgets import (
    PushButton, PrimaryPushButton, TextEdit,
    CaptionLabel,
)


class MessageBubble(QFrame):
    """单条消息气泡"""

    def __init__(self, role: str, content: str, timestamp: str = "", parent=None):
        super().__init__(parent)
        self.role = role
        is_user = role == "user"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignRight if is_user else Qt.AlignLeft)

        role_label = CaptionLabel("你" if is_user else "AI")
        role_label.setStyleSheet(
            "color: #2ecc71; font-weight: bold;" if is_user else "color: #3498db; font-weight: bold;"
        )
        if timestamp:
            role_label.setText(f"{role_label.text()}  {timestamp}")
        if is_user:
            role_label.setAlignment(Qt.AlignRight)
        layout.addWidget(role_label)

        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.PlainText)
        content_label.setStyleSheet(
            f"""
            QLabel {{
                background-color: {'#d5f5e3' if is_user else '#d6eaf8'};
                border-radius: 8px;
                padding: 10px 14px;
                color: #1a1a1a;
                font-size: 13px;
            }}
            """
        )
        layout.addWidget(content_label)

        self.setStyleSheet("""MessageBubble { background: transparent; margin: 4px 8px; }""")


class ChatWidget(QWidget):
    """多轮对话组件 — 消息气泡列表 + 输入区 + 流式更新"""

    message_sent = Signal(str)
    clear_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stream_bubble: MessageBubble | None = None
        self._stream_content: str = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.message_container = QWidget()
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.setContentsMargins(8, 8, 8, 8)
        self.message_layout.setSpacing(4)
        self.message_layout.addStretch()

        self.scroll.setWidget(self.message_container)
        layout.addWidget(self.scroll, 1)

        input_frame = QFrame()
        input_frame.setStyleSheet("QFrame { background: #f8f9fa; border-radius: 8px; }")
        input_ly = QVBoxLayout(input_frame)
        input_ly.setContentsMargins(12, 8, 12, 8)
        input_ly.setSpacing(8)

        self.chat_input = TextEdit()
        self.chat_input.setPlaceholderText("输入消息，Enter 发送，Shift+Enter 换行...")
        self.chat_input.setFixedHeight(70)
        self.chat_input.setFont(QFont("Microsoft YaHei", 11))
        input_ly.addWidget(self.chat_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self.btn_clear = PushButton("清空对话")
        btn_row.addWidget(self.btn_clear)

        self.btn_send = PrimaryPushButton("发送")
        btn_row.addWidget(self.btn_send)

        input_ly.addLayout(btn_row)
        layout.addWidget(input_frame)

        self.chat_input.keyPressEvent = self._on_key_press

    def _on_key_press(self, event):
        if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
            self._send()
        else:
            QTextEdit.keyPressEvent(self.chat_input, event)

    def _send(self):
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        self.add_message("user", text)
        self.chat_input.clear()
        self.message_sent.emit(text)

    def add_message(self, role: str, content: str, timestamp: str = ""):
        bubble = MessageBubble(role, content, timestamp)
        self.message_layout.insertWidget(self.message_layout.count() - 1, bubble)
        self._scroll_to_bottom()

    def start_stream_message(self):
        self._stream_content = ""
        self._stream_bubble = MessageBubble("assistant", "")
        self.message_layout.insertWidget(self.message_layout.count() - 1, self._stream_bubble)

    def append_stream_chunk(self, text: str):
        self._stream_content += text
        if self._stream_bubble:
            self._stream_bubble.deleteLater()
            self._stream_bubble = MessageBubble("assistant", self._stream_content)
            self.message_layout.insertWidget(self.message_layout.count() - 1, self._stream_bubble)
        self._scroll_to_bottom()

    @property
    def stream_content(self) -> str:
        return self._stream_content

    def finish_stream(self):
        self._stream_bubble = None
        self._stream_content = ""

    def clear_messages(self):
        while self.message_layout.count() > 1:
            item = self.message_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.clear_requested.emit()

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))
