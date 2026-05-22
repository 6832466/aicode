from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox,
)

from app.config import app_icon_path


class LicenseDialog(QDialog):
    """License verification dialog shown once at first launch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("许可证验证")
        self.setFixedSize(420, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._set_icon()
        self._setup_ui()

    def _set_icon(self):
        try:
            p = app_icon_path()
            if p.exists():
                self.setWindowIcon(QIcon(str(p)))
        except Exception:
            pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        title = QLabel("请输入许可证密钥以继续使用")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("请联系管理员获取许可证密钥")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        self._input = QLineEdit()
        self._input.setPlaceholderText("请输入中文许可证密钥…")
        self._input.setEchoMode(QLineEdit.Normal)
        self._input.setFixedHeight(32)
        self._input.returnPressed.connect(self._on_verify)
        layout.addWidget(self._input)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_verify = QPushButton("验证")
        self._btn_verify.setFixedWidth(80)
        self._btn_verify.setFixedHeight(32)
        self._btn_verify.clicked.connect(self._on_verify)
        self._btn_verify.setStyleSheet(
            "QPushButton { background-color: #1976D2; color: white; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1565C0; }"
        )

        btn_layout.addWidget(self._btn_verify)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _on_verify(self):
        from app.license import verify_passphrase

        passphrase = self._input.text().strip()
        if not passphrase:
            QMessageBox.warning(self, "输入错误", "请输入许可证密钥。")
            return

        if verify_passphrase(passphrase):
            self.accept()
        else:
            self._input.clear()
            self._input.setFocus()
            QMessageBox.warning(
                self, "验证失败",
                "许可证密钥不正确，请重新输入。\n\n如有疑问请联系管理员。",
            )
