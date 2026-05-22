"""登录对话框 - 复用组件"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QLineEdit, QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class LoginDialog(QDialog):
    """统一的登录对话框，支持多种登录形态"""

    def __init__(self, title: str, subtitle: str = "",
                 has_nickname: bool = False, has_cookie: bool = False,
                 has_phone: bool = False, has_password: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.setStyleSheet("""
            QDialog {
                background: #FFFFFF;
            }
            QLabel {
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }
            QTextEdit, QLineEdit {
                border: 1px solid #D0D0D0;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                background: #F9F9F9;
            }
            QTextEdit:focus, QLineEdit:focus {
                border-color: #0078D4;
                background: #FFFFFF;
            }
            QPushButton {
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
            }
        """)

        self._nickname_input = None
        self._cookie_input = None
        self._phone_input = None
        self._password_input = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Subtitle
        if subtitle:
            label = QLabel(subtitle)
            label.setWordWrap(True)
            label.setStyleSheet('font-size: 13px; color: #333;')
            layout.addWidget(label)

        # Nickname
        if has_nickname:
            layout.addWidget(QLabel('账号昵称（可选）：'))
            self._nickname_input = QLineEdit()
            self._nickname_input.setPlaceholderText('输入一个名称用于区分账号')
            layout.addWidget(self._nickname_input)

        # Cookie
        if has_cookie:
            layout.addWidget(QLabel('Cookie 内容：'))
            self._cookie_input = QTextEdit()
            self._cookie_input.setPlaceholderText('粘贴完整的 Cookie 字符串...')
            self._cookie_input.setMinimumHeight(100)
            layout.addWidget(self._cookie_input)

        # Phone
        if has_phone:
            layout.addWidget(QLabel('手机号/邮箱：'))
            self._phone_input = QLineEdit()
            self._phone_input.setPlaceholderText('请输入绑定的手机号或邮箱')
            layout.addWidget(self._phone_input)

        # Password
        if has_password:
            layout.addWidget(QLabel('密码：'))
            self._password_input = QLineEdit()
            self._password_input.setEchoMode(QLineEdit.Password)
            self._password_input.setPlaceholderText('请输入密码')
            layout.addWidget(self._password_input)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton('取消')
        cancel_btn.setStyleSheet('background: #E0E0E0; color: #333;')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton('确认')
        ok_btn.setStyleSheet('background: #0078D4; color: white;')
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    @property
    def nickname_value(self) -> str:
        return self._nickname_input.text().strip() if self._nickname_input else ""

    @property
    def cookie_value(self) -> str:
        return self._cookie_input.toPlainText().strip() if self._cookie_input else ""

    @property
    def phone_value(self) -> str:
        return self._phone_input.text().strip() if self._phone_input else ""

    @property
    def password_value(self) -> str:
        return self._password_input.text().strip() if self._password_input else ""
