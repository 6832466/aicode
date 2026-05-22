"""API connection settings dialog (OpenAI-compatible protocol)."""
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QComboBox, QLineEdit, QButtonGroup,
    QFileDialog,
)
from PySide6.QtCore import QUrl
from qfluentwidgets import (
    LineEdit, PushButton, PrimaryPushButton, ComboBox, ToolButton,
    CardWidget, InfoBar, InfoBarPosition, FluentIcon, BodyLabel, RadioButton,
)

from api_client import Flow2ApiClient
from gemini_cdp import GeminiCDPClient
from config import cfg
from server_manager import read_flow2api_config
from cookie_util import CookieLoginDialog

# Preset remote API configurations
API_PRESETS = {
    "bj.nfai.lol": {
        "name": "豹剪 API (bj.nfai.lol)",
        "url": "https://bj.nfai.lol/pg",
        "key": "",
        "model": "gemini-2.5-flash-image",
        "path": "/chat/completions",
        "user_id": "13679",
        "group": "default",
    },
    "custom": {
        "name": "自定义",
        "url": "",
        "key": "",
        "model": "gemini-2.5-flash-image",
        "path": "/chat/completions",
        "user_id": "",
        "group": "default",
    },
}

# Image generation models for remote mode (per-request, under $0.20)
IMAGE_GEN_MODELS = [
    ("gemini-2.5-flash-image — $0.033/次", "gemini-2.5-flash-image"),
    ("gemini-2.5-flash-image-preview — $0.033/次", "gemini-2.5-flash-image-preview"),
    ("gpt-image-2 — $0.042/次", "gpt-image-2"),
    ("gpt-image-2-1k — $0.042/次", "gpt-image-2-1k"),
    ("gpt-image-2-2k — $0.082/次", "gpt-image-2-2k"),
    ("gpt-image-2-4k — $0.082/次", "gpt-image-2-4k"),
    ("gemini-3.1-flash-image-preview-url — $0.090/次", "gemini-3.1-flash-image-preview-url"),
    ("gemini-3-pro-image-preview-url — $0.180/次", "gemini-3-pro-image-preview-url"),
    ("gemini-3-pro-image-preview — $0.190/次", "gemini-3-pro-image-preview"),
]

# Recharge URL
RECHARGE_URL = "https://bj.nfai.lol/console/topup"


class _ConnectionTester(QThread):
    """Background thread for testing API connection."""
    finished = Signal(bool, str)

    def __init__(self, base_url: str, api_key: str, endpoint_path: str = "/v1/chat/completions",
                 session_cookie: str = "", user_id: str = "", group: str = "default"):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.endpoint_path = endpoint_path
        self.session_cookie = session_cookie
        self.user_id = user_id
        self.group = group

    def run(self):
        try:
            client = Flow2ApiClient(self.base_url, self.api_key, endpoint_path=self.endpoint_path,
                                    session_cookie=self.session_cookie, user_id=self.user_id,
                                    group=self.group)
            ok, msg = client.check_connection()
            self.finished.emit(ok, msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class _CDPConnectionTester(QThread):
    """Background thread for testing Chrome CDP connection."""
    finished = Signal(bool, str)

    def run(self):
        try:
            client = GeminiCDPClient()
            ok, msg = client.check_connection()
            self.finished.emit(ok, msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class SettingsDialog(QDialog):
    """Dialog for configuring OpenAI-compatible API connection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API 连接设置")
        self.setMinimumSize(560, 780)
        self.resize(560, 780)
        self.setModal(True)
        self._tester: _ConnectionTester | None = None

        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        header = QLabel("OpenAI 兼容协议配置")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        layout.addWidget(header)

        hint = QLabel(
            "本地模式通过 Chrome CDP 直连 Gemini 网页；"
            "远程模式兼容 OpenAI /v1/chat/completions 协议端点"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(hint)

        # API mode
        mode_label = QLabel("API 模式")
        mode_label.setStyleSheet("font-weight: bold; color: #555; margin-top: 4px;")
        layout.addWidget(mode_label)
        self.local_radio = RadioButton("本地 Chrome (CDP 直连 Gemini)")
        self.remote_radio = RadioButton("远程 API (OpenAI 兼容)")
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.local_radio, 0)
        self._mode_group.addButton(self.remote_radio, 1)
        self._mode_group.idToggled.connect(self._on_mode_changed)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(20)
        mode_row.addWidget(self.local_radio)
        mode_row.addWidget(self.remote_radio)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Chrome executable path (local mode only)
        self.chrome_path_label = QLabel("Chrome 浏览器路径")
        self.chrome_path_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(self.chrome_path_label)
        chrome_path_row = QHBoxLayout()
        chrome_path_row.setSpacing(6)
        self.chrome_path_edit = LineEdit()
        self.chrome_path_edit.setPlaceholderText("自动检测或手动选择 chrome.exe 路径")
        chrome_path_row.addWidget(self.chrome_path_edit, 1)
        self.chrome_browse_btn = PushButton("浏览")
        self.chrome_browse_btn.setFixedWidth(60)
        self.chrome_browse_btn.clicked.connect(self._browse_chrome_path)
        chrome_path_row.addWidget(self.chrome_browse_btn)
        layout.addLayout(chrome_path_row)

        chrome_path_hint = QLabel(
            "留空则自动检测 Chrome 安装位置。"
            "手动指定时请确保 Chrome 版本支持远程调试端口 (--remote-debugging-port)。"
        )
        chrome_path_hint.setWordWrap(True)
        chrome_path_hint.setStyleSheet("color: #999; font-size: 11px;")
        self.chrome_path_hint = chrome_path_hint
        layout.addWidget(self.chrome_path_hint)

        # Preset selector (remote only)
        preset_label = QLabel("API 预设")
        preset_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(preset_label)
        self.preset_label = preset_label
        self.preset_combo = ComboBox()
        for key, preset in API_PRESETS.items():
            self.preset_combo.addItem(preset["name"], userData=key)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        layout.addWidget(self.preset_combo)

        # Base URL
        self.url_label = QLabel("API Base URL")
        self.url_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(self.url_label)
        self.url_edit = LineEdit()
        self.url_edit.setPlaceholderText("http://localhost:8000")
        layout.addWidget(self.url_edit)

        # Endpoint Path
        self.path_label = QLabel("API Endpoint Path")
        self.path_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(self.path_label)
        self.path_edit = LineEdit()
        self.path_edit.setPlaceholderText("/v1/chat/completions")
        layout.addWidget(self.path_edit)

        # API Key
        self.key_label = QLabel("API Key")
        self.key_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(self.key_label)
        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        self.key_edit = LineEdit()
        self.key_edit.setPlaceholderText("输入 API Key")
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(self.key_edit, 1)
        self.key_toggle_btn = ToolButton(FluentIcon.VIEW)
        self.key_toggle_btn.setFixedSize(30, 30)
        self.key_toggle_btn.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.key_toggle_btn)
        layout.addLayout(key_row)

        # Session Cookie (for servers that disable Bearer token, e.g. New API)
        cookie_label = QLabel("Session Cookie (会话认证)")
        cookie_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(cookie_label)
        self.cookie_label = cookie_label
        cookie_row = QHBoxLayout()
        cookie_row.setSpacing(6)
        self.cookie_edit = LineEdit()
        self.cookie_edit.setPlaceholderText("从浏览器中获取 session cookie 值")
        self.cookie_edit.setEchoMode(QLineEdit.EchoMode.Password)
        cookie_row.addWidget(self.cookie_edit, 1)
        self.cookie_toggle_btn = ToolButton(FluentIcon.VIEW)
        self.cookie_toggle_btn.setFixedSize(30, 30)
        self.cookie_toggle_btn.clicked.connect(self._toggle_cookie_visibility)
        cookie_row.addWidget(self.cookie_toggle_btn)
        self.cookie_login_btn = PushButton("获取")
        self.cookie_login_btn.setMinimumWidth(56)
        self.cookie_login_btn.setFixedHeight(30)
        self.cookie_login_btn.clicked.connect(self._on_cookie_login)
        cookie_row.addWidget(self.cookie_login_btn)
        layout.addLayout(cookie_row)

        self.cookie_hint = QLabel(
            "点击右侧「获取」按钮 → 在弹出窗口中登录 → 自动填充 Cookie。"
            "也可手动从浏览器 F12 → Application → Cookies 复制 session 值。"
        )
        self.cookie_hint.setWordWrap(True)
        self.cookie_hint.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(self.cookie_hint)

        # User ID (for New API user header)
        uid_label = QLabel("User ID (new-api-user)")
        uid_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(uid_label)
        self.uid_label = uid_label
        self.uid_edit = LineEdit()
        self.uid_edit.setPlaceholderText("13679")
        layout.addWidget(self.uid_edit)

        # Model
        self.model_label = QLabel("默认模型")
        self.model_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(self.model_label)

        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(320)
        self.model_combo.setPlaceholderText("输入模型名或从下拉列表选择")
        model_row.addWidget(self.model_combo, 1)
        self.recharge_btn = PushButton("充值")
        self.recharge_btn.setFixedWidth(60)
        self.recharge_btn.clicked.connect(self._on_recharge)
        model_row.addWidget(self.recharge_btn)
        layout.addLayout(model_row)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.test_btn = PushButton("测试连接")
        self.test_btn.setIcon(FluentIcon.WIFI)
        self.test_btn.clicked.connect(self._on_test_connection)
        btn_row.addWidget(self.test_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px;")
        btn_row.addWidget(self.status_label, 1)

        self.cancel_btn = PushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.save_btn = PrimaryPushButton("保存")
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)

        layout.addLayout(btn_row)


    def _populate_model_combo(self, is_remote: bool):
        self.model_combo.clear()
        if is_remote:
            for label, model in IMAGE_GEN_MODELS:
                self.model_combo.addItem(label, model)
        else:
            self.model_combo.addItem("gemini-3.1-flash-image", "gemini-3.1-flash-image")

    def _apply_local_defaults(self):
        self.url_edit.setText("")  # Not used in local CDP mode
        self.path_edit.setText("/v1/chat/completions")
        self.key_edit.clear()
        idx = self.model_combo.findData("gemini-3.1-flash-image")
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setCurrentText("gemini-3.1-flash-image")

    def _load_config(self):
        # Block signals so _on_mode_changed / _on_preset_changed don't fire during init
        self._mode_group.blockSignals(True)
        self.preset_combo.blockSignals(True)

        if cfg.use_local_server.value:
            self.local_radio.setChecked(True)
        else:
            self.remote_radio.setChecked(True)

        preset_key = cfg.remote_preset.value
        idx = self.preset_combo.findData(preset_key)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)

        self._mode_group.blockSignals(False)
        self.preset_combo.blockSignals(False)

        # Populate model combo based on current mode
        self._populate_model_combo(not cfg.use_local_server.value)

        # Apply mode-specific defaults, then override with saved config
        if cfg.use_local_server.value:
            self._apply_local_defaults()
            # Override with saved values for fields the user may have customized
            if cfg.api_base_url.value:
                self.url_edit.setText(cfg.api_base_url.value)
            if cfg.api_endpoint_path.value:
                self.path_edit.setText(cfg.api_endpoint_path.value)
            if cfg.api_key.value:
                self.key_edit.setText(cfg.api_key.value)
            model = cfg.model_name.value
            model_idx = self.model_combo.findData(model)
            if model_idx >= 0:
                self.model_combo.setCurrentIndex(model_idx)
            elif model:
                self.model_combo.setCurrentText(model)
        else:
            if preset_key != "custom":
                self._apply_preset()
                # Override model with saved preference (preset default is just a starting point)
                model = cfg.model_name.value
                model_idx = self.model_combo.findData(model)
                if model_idx >= 0:
                    self.model_combo.setCurrentIndex(model_idx)
                elif model:
                    self.model_combo.setCurrentText(model)
            else:
                # Custom remote: load saved values
                if cfg.api_base_url.value:
                    self.url_edit.setText(cfg.api_base_url.value)
                if cfg.api_endpoint_path.value:
                    self.path_edit.setText(cfg.api_endpoint_path.value)
                if cfg.api_key.value:
                    self.key_edit.setText(cfg.api_key.value)
                else:
                    self.key_edit.clear()
                model = cfg.model_name.value
                model_idx = self.model_combo.findData(model)
                if model_idx >= 0:
                    self.model_combo.setCurrentIndex(model_idx)
                elif model:
                    self.model_combo.setCurrentText(model)
            # Session cookie & user ID always loaded from saved config
            if cfg.api_session_cookie.value:
                self.cookie_edit.setText(cfg.api_session_cookie.value)
            else:
                self.cookie_edit.clear()
            if cfg.api_user_id.value:
                self.uid_edit.setText(cfg.api_user_id.value)
            else:
                self.uid_edit.clear()

        if cfg.chrome_exe_path.value:
            self.chrome_path_edit.setText(cfg.chrome_exe_path.value)
        else:
            self.chrome_path_edit.clear()

        self._update_field_visibility()

    def _update_field_visibility(self):
        is_remote = self.remote_radio.isChecked()
        # API fields: visible only in remote mode
        self.preset_label.setVisible(is_remote)
        self.preset_combo.setVisible(is_remote)
        self.url_label.setVisible(is_remote)
        self.url_edit.setVisible(is_remote)
        self.path_label.setVisible(is_remote)
        self.path_edit.setVisible(is_remote)
        self.key_label.setVisible(is_remote)
        self.key_edit.setVisible(is_remote)
        self.key_toggle_btn.setVisible(is_remote)
        self.cookie_label.setVisible(is_remote)
        self.cookie_edit.setVisible(is_remote)
        self.cookie_toggle_btn.setVisible(is_remote)
        self.cookie_login_btn.setVisible(is_remote)
        self.cookie_hint.setVisible(is_remote)
        self.uid_label.setVisible(is_remote)
        self.uid_edit.setVisible(is_remote)
        self.model_label.setVisible(is_remote)
        self.recharge_btn.setVisible(is_remote)
        self.model_combo.setVisible(is_remote)
        # Chrome path fields: visible only in local mode
        self.chrome_path_label.setVisible(not is_remote)
        self.chrome_path_edit.setVisible(not is_remote)
        self.chrome_browse_btn.setVisible(not is_remote)
        self.chrome_path_hint.setVisible(not is_remote)

    def _on_mode_changed(self, id: int, checked: bool):
        if not checked:
            return
        is_remote = (id == 1)
        self._update_field_visibility()
        self._populate_model_combo(is_remote)
        if is_remote:
            if self.preset_combo.currentData() != "custom":
                self._apply_preset()
                # Restore saved model preference
                model = cfg.model_name.value
                model_idx = self.model_combo.findData(model)
                if model_idx >= 0:
                    self.model_combo.setCurrentIndex(model_idx)
                elif model:
                    self.model_combo.setCurrentText(model)
            # Restore saved session cookie and user ID (may not be in preset)
            if cfg.api_session_cookie.value:
                self.cookie_edit.setText(cfg.api_session_cookie.value)
            else:
                self.cookie_edit.clear()
            if cfg.api_user_id.value:
                self.uid_edit.setText(cfg.api_user_id.value)
            else:
                self.uid_edit.clear()
        else:
            self._apply_local_defaults()

    def _on_preset_changed(self):
        if not self.remote_radio.isChecked():
            return
        self._populate_model_combo(True)
        self._apply_preset()
        # Restore saved model preference over preset default
        model = cfg.model_name.value
        model_idx = self.model_combo.findData(model)
        if model_idx >= 0:
            self.model_combo.setCurrentIndex(model_idx)
        elif model:
            self.model_combo.setCurrentText(model)

    def _apply_preset(self):
        key = self.preset_combo.currentData()
        if key is None or key == "custom":
            return
        preset = API_PRESETS.get(key)
        if preset:
            self.url_edit.setText(preset["url"])
            if preset["key"]:
                self.key_edit.setText(preset["key"])
            else:
                self.key_edit.clear()
            self.path_edit.setText(preset.get("path", "/v1/chat/completions"))
            self.uid_edit.setText(preset.get("user_id", ""))
            # Don't overwrite session cookie with preset (session-specific)
            model = preset["model"]
            idx = self.model_combo.findData(model)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            else:
                self.model_combo.setCurrentText(model)

    def _toggle_key_visibility(self):
        if self.key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.key_toggle_btn.setIcon(FluentIcon.HIDE)
        else:
            self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.key_toggle_btn.setIcon(FluentIcon.VIEW)

    def _toggle_cookie_visibility(self):
        if self.cookie_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.cookie_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.cookie_toggle_btn.setIcon(FluentIcon.HIDE)
        else:
            self.cookie_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.cookie_toggle_btn.setIcon(FluentIcon.VIEW)

    def _browse_chrome_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Chrome 可执行文件",
            str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application"),
            "Executables (*.exe)"
        )
        if path:
            self.chrome_path_edit.setText(path)

    def _on_recharge(self):
        QDesktopServices.openUrl(QUrl(RECHARGE_URL))

    def _on_cookie_login(self):
        try:
            dlg = CookieLoginDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                if dlg.session_cookie:
                    self.cookie_edit.setText(dlg.session_cookie)
                    cfg.api_session_cookie.value = dlg.session_cookie
                if dlg.user_id:
                    self.uid_edit.setText(dlg.user_id)
                    cfg.api_user_id.value = dlg.user_id
                cfg.save()
                InfoBar.success(
                    title="Cookie 已获取",
                    content="Session Cookie 和 User ID 已自动填入并保存",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
        except Exception as e:
            InfoBar.error(
                title="获取失败",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )

    def _on_test_connection(self):
        self.test_btn.setEnabled(False)
        self.status_label.setText("正在测试…")
        self.status_label.setStyleSheet("color: #f0ad4e; font-size: 12px;")

        if self.local_radio.isChecked():
            # Local mode: test Chrome CDP connection
            self._tester = _CDPConnectionTester()
        else:
            # Remote mode: test API connection
            base_url = self.url_edit.text().strip()
            api_key = self.key_edit.text().strip()
            endpoint_path = self.path_edit.text().strip() or "/v1/chat/completions"
            session_cookie = self.cookie_edit.text().strip()
            user_id = self.uid_edit.text().strip()
            group = "default"
            if not base_url:
                self.status_label.setText("请输入 API Base URL")
                self.status_label.setStyleSheet("color: #d9534f; font-size: 12px;")
                self.test_btn.setEnabled(True)
                return
            self._tester = _ConnectionTester(base_url, api_key, endpoint_path,
                                             session_cookie=session_cookie,
                                             user_id=user_id, group=group)
        self._tester.finished.connect(self._on_test_result)
        self._tester.start()

    def _on_test_result(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        if ok:
            self.status_label.setText("连接成功")
            self.status_label.setStyleSheet("color: #5cb85c; font-size: 12px;")
        else:
            self.status_label.setText(f"连接失败: {msg}")
            self.status_label.setStyleSheet("color: #d9534f; font-size: 12px;")

    def _on_save(self):
        cfg.api_base_url.value = self.url_edit.text().strip()
        cfg.api_key.value = self.key_edit.text().strip()
        cfg.api_endpoint_path.value = self.path_edit.text().strip() or "/v1/chat/completions"
        cfg.model_name.value = self.model_combo.currentData() or self.model_combo.currentText().strip()
        cfg.use_local_server.value = self.local_radio.isChecked()
        cfg.remote_preset.value = self.preset_combo.currentData() or "custom"
        cfg.api_session_cookie.value = self.cookie_edit.text().strip()
        cfg.api_user_id.value = self.uid_edit.text().strip()
        cfg.chrome_exe_path.value = self.chrome_path_edit.text().strip()
        cfg.save()
        self.accept()
