"""设置页面 —— 保存目录、Chrome 用户数据目录。选择即自动保存。"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QFileDialog,
)

from qfluentwidgets import (
    TitleLabel, BodyLabel,
    LineEdit, PushButton,
    SimpleCardWidget,
    FluentIcon,
)

from core.config import app_config


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(16)

        title = TitleLabel("设置")
        root.addWidget(title)

        # ── 默认保存目录 ──
        dir_card = SimpleCardWidget()
        dir_layout = QFormLayout(dir_card)
        dir_layout.setContentsMargins(20, 16, 20, 16)
        dir_layout.setSpacing(12)

        dir_row = QHBoxLayout()
        self._output_dir_edit = LineEdit()
        self._output_dir_edit.setPlaceholderText("选择默认保存目录...")
        self._output_dir_edit.setReadOnly(True)
        self._output_dir_edit.textChanged.connect(self._on_output_dir_changed)
        dir_row.addWidget(self._output_dir_edit, stretch=1)

        browse_btn = PushButton(FluentIcon.FOLDER, "浏览")
        browse_btn.clicked.connect(self._on_browse_output)
        dir_row.addWidget(browse_btn)

        dir_layout.addRow(BodyLabel("默认保存目录"), dir_row)
        root.addWidget(dir_card)

        # ── Chrome 用户数据目录 ──
        profile_card = SimpleCardWidget()
        profile_layout = QFormLayout(profile_card)
        profile_layout.setContentsMargins(20, 16, 20, 16)
        profile_layout.setSpacing(12)

        profile_row = QHBoxLayout()
        self._profile_dir_edit = LineEdit()
        self._profile_dir_edit.setPlaceholderText("Chrome 用户数据目录 (用于保存登录状态)...")
        self._profile_dir_edit.setReadOnly(True)
        self._profile_dir_edit.textChanged.connect(self._on_profile_dir_changed)
        profile_row.addWidget(self._profile_dir_edit, stretch=1)

        browse2_btn = PushButton(FluentIcon.FOLDER, "浏览")
        browse2_btn.clicked.connect(self._on_browse_profile)
        profile_row.addWidget(browse2_btn)

        profile_layout.addRow(BodyLabel("Chrome 用户数据目录"), profile_row)
        root.addWidget(profile_card)

        root.addStretch()

    def _load_config(self):
        self._output_dir_edit.blockSignals(True)
        self._profile_dir_edit.blockSignals(True)
        if app_config.output_dir.value:
            self._output_dir_edit.setText(app_config.output_dir.value)
        if app_config.user_data_dir.value:
            self._profile_dir_edit.setText(app_config.user_data_dir.value)
        self._output_dir_edit.blockSignals(False)
        self._profile_dir_edit.blockSignals(False)

    def _on_browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if path:
            self._output_dir_edit.setText(path)

    def _on_browse_profile(self):
        path = QFileDialog.getExistingDirectory(self, "选择 Chrome 用户数据目录")
        if path:
            self._profile_dir_edit.setText(path)

    def _on_output_dir_changed(self, text: str):
        path = text.strip()
        if path and os.path.isdir(path):
            app_config.set(app_config.output_dir, path)

    def _on_profile_dir_changed(self, text: str):
        path = text.strip()
        if path and os.path.isdir(path):
            app_config.set(app_config.user_data_dir, path)
