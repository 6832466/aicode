"""API 设置页面 —— 豹剪 API 专用。"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QFrame, QLineEdit, QPushButton, QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from qfluentwidgets import (
    TitleLabel, BodyLabel, CaptionLabel,
    LineEdit, EditableComboBox,
    PrimaryPushButton, PushButton,
    SimpleCardWidget,
    FluentIcon, InfoBar, InfoBarPosition,
)

from api_config import api_config, get_session_cookie, get_user_id, set_session_cookie, set_user_id, get_img_save_dir, set_img_save_dir, MODEL_CHOICES

# 豹剪 API 固定值
BJ_BASE_URL = "https://bj.nfai.lol/pg"
BJ_DEFAULT_UID = "13679"
BJ_TOPUP_URL = "https://bj.nfai.lol/console/topup"


# ── 带切换按钮的密码输入 ─────────────────────────────────────

class _PasswordRow(QWidget):
    """LineEdit（密码模式）+ 显示/隐藏切换按钮。"""

    def __init__(self, placeholder: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.edit = LineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.edit, stretch=1)

        self._toggle = QPushButton("👁")
        self._toggle.setFixedSize(28, 28)
        self._toggle.setCheckable(True)
        self._toggle.setFlat(True)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.toggled.connect(self._on_toggle)
        layout.addWidget(self._toggle)

    def _on_toggle(self, checked: bool) -> None:
        if checked:
            self.edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle.setText("✕")
        else:
            self.edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle.setText("👁")

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str) -> None:
        self.edit.setText(value)

    def setPlaceholderText(self, value: str) -> None:
        self.edit.setPlaceholderText(value)

    def setFixedWidth(self, w: int) -> None:
        self.edit.setFixedWidth(w - 32)


# ── 后台连接测试线程 ─────────────────────────────────────────

class ConnectionTestThread(QThread):
    result_ready = Signal(bool, str)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self._config = config

    def run(self) -> None:
        import json as _json
        import requests
        try:
            headers = {"Content-Type": "application/json"}
            cookie = self._config.get("session_cookie", "")
            api_key = self._config.get("api_key", "")
            user_id = get_user_id()

            if not cookie and not api_key:
                self.result_ready.emit(False, "请先配置 Session Cookie 或 API Key")
                return

            if cookie:
                headers["Cookie"] = f"session={cookie}"
                headers["new-api-user"] = user_id
            elif api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # 用 /api/status 验证连通性与认证
            url = f"{BJ_BASE_URL}/api/status"
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code in (401, 403):
                self.result_ready.emit(False, "认证失败，请检查 Cookie 或 API Key")
                return

            if resp.status_code != 200:
                self.result_ready.emit(False, f"服务器返回 HTTP {resp.status_code}")
                return

            # 检查响应体中是否包含错误信息
            try:
                body = resp.json()
            except _json.JSONDecodeError:
                body = {}
            if isinstance(body, dict) and body.get("error"):
                self.result_ready.emit(False, str(body["error"]))
                return

            self.result_ready.emit(True, "连接成功")
        except requests.exceptions.Timeout:
            self.result_ready.emit(False, "连接超时")
        except requests.exceptions.ConnectionError:
            self.result_ready.emit(False, "无法连接服务器")
        except Exception as e:
            self.result_ready.emit(False, str(e))


# ── 设置页面 ─────────────────────────────────────────────────

class SettingsPage(QWidget):
    """豹剪 API 设置页。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._test_thread: ConnectionTestThread | None = None
        self._build_ui()
        self._load_config()

    # ── UI 构建 ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(16)

        # ── 页头 ──
        header = QHBoxLayout()
        title = TitleLabel("设置")
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        hint = CaptionLabel(f"服务地址：{BJ_BASE_URL}  |  豹剪 API")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ── 密钥卡片 ──
        key_card = SimpleCardWidget()
        key_layout = QFormLayout(key_card)
        key_layout.setContentsMargins(20, 16, 20, 16)
        key_layout.setSpacing(12)

        self._key_row = _PasswordRow("输入 API Key")
        key_layout.addRow(BodyLabel("API Key"), self._key_row)

        root.addWidget(key_card)

        # ── 认证卡片 ──
        auth_card = SimpleCardWidget()
        auth_layout = QFormLayout(auth_card)
        auth_layout.setContentsMargins(20, 16, 20, 16)
        auth_layout.setSpacing(12)

        cookie_row = QHBoxLayout()
        self._cookie_row = _PasswordRow("从浏览器中获取 session cookie 值")
        cookie_row.addWidget(self._cookie_row, stretch=1)

        fetch_btn = PushButton("获取")
        fetch_btn.clicked.connect(self._on_fetch_cookie)
        cookie_row.addWidget(fetch_btn)
        cookie_row.addSpacing(4)

        cookie_wrapper = QVBoxLayout()
        cookie_wrapper.addLayout(cookie_row)
        cookie_hint = CaptionLabel("点击按钮 → 在弹出窗口中登录 → 自动填充并持久化")
        cookie_hint.setWordWrap(True)
        cookie_wrapper.addWidget(cookie_hint)
        auth_layout.addRow(BodyLabel("Session Cookie"), cookie_wrapper)

        self._uid_edit = LineEdit()
        self._uid_edit.setPlaceholderText(BJ_DEFAULT_UID)
        self._uid_edit.setFixedWidth(420)
        self._uid_edit.setReadOnly(True)
        auth_layout.addRow(BodyLabel("User ID（登录后自动获取）"), self._uid_edit)

        root.addWidget(auth_card)

        # ── 模型卡片 ──
        model_card = SimpleCardWidget()
        model_layout = QFormLayout(model_card)
        model_layout.setContentsMargins(20, 16, 20, 16)
        model_layout.setSpacing(12)

        model_row = QHBoxLayout()
        self._model_combo = EditableComboBox()
        self._model_combo.setPlaceholderText("输入模型名或从下拉列表选择")
        self._model_combo.setFixedWidth(340)
        for display, model_id in MODEL_CHOICES:
            self._model_combo.addItem(display, userData=model_id)
        self._model_combo.setCurrentIndex(0)
        model_row.addWidget(self._model_combo)

        topup_btn = PushButton("充值")
        topup_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(BJ_TOPUP_URL))
        )
        model_row.addWidget(topup_btn)
        model_row.addStretch()
        model_layout.addRow(BodyLabel("默认模型"), model_row)

        root.addWidget(model_card)

        # ── 生图提示词卡片 ──
        img_card = SimpleCardWidget()
        img_layout = QFormLayout(img_card)
        img_layout.setContentsMargins(20, 16, 20, 16)
        img_layout.setSpacing(12)

        self._img_prefix_edit = LineEdit()
        self._img_prefix_edit.setPlaceholderText("生图提示词前缀…")
        img_layout.addRow(BodyLabel("生图 - 前缀"), self._img_prefix_edit)

        self._img_suffix_edit = LineEdit()
        self._img_suffix_edit.setPlaceholderText("生图提示词后缀…")
        img_layout.addRow(BodyLabel("生图 - 后缀"), self._img_suffix_edit)

        root.addWidget(img_card)

        # ── 生视频提示词卡片 ──
        vid_card = SimpleCardWidget()
        vid_layout = QFormLayout(vid_card)
        vid_layout.setContentsMargins(20, 16, 20, 16)
        vid_layout.setSpacing(12)

        self._vid_prefix_edit = LineEdit()
        self._vid_prefix_edit.setPlaceholderText("生视频提示词前缀…")
        vid_layout.addRow(BodyLabel("生视频 - 前缀"), self._vid_prefix_edit)

        self._vid_suffix_edit = LineEdit()
        self._vid_suffix_edit.setPlaceholderText("生视频提示词后缀…")
        vid_layout.addRow(BodyLabel("生视频 - 后缀"), self._vid_suffix_edit)

        root.addWidget(vid_card)

        # ── 图片保存目录卡片 ──
        dir_card = SimpleCardWidget()
        dir_layout = QFormLayout(dir_card)
        dir_layout.setContentsMargins(20, 16, 20, 16)
        dir_layout.setSpacing(12)

        dir_row = QHBoxLayout()
        self._save_dir_edit = LineEdit()
        self._save_dir_edit.setPlaceholderText("默认：软件目录/generated")
        self._save_dir_edit.setReadOnly(True)
        dir_row.addWidget(self._save_dir_edit, stretch=1)

        browse_btn = PushButton("浏览")
        browse_btn.clicked.connect(self._on_browse_save_dir)
        dir_row.addWidget(browse_btn)
        dir_layout.addRow(BodyLabel("图片保存目录"), dir_row)

        root.addWidget(dir_card)

        root.addStretch()

        # ── 底部操作栏 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        footer = QHBoxLayout()
        footer.setSpacing(12)

        self._test_btn = PushButton(FluentIcon.WIFI, "测试连接")
        self._test_btn.clicked.connect(self._on_test_connection)
        footer.addWidget(self._test_btn)

        self._status_label = BodyLabel("")
        footer.addWidget(self._status_label)
        footer.addStretch()

        save_btn = PrimaryPushButton(FluentIcon.SAVE, "保存配置")
        save_btn.clicked.connect(self._on_save)
        footer.addWidget(save_btn)

        root.addLayout(footer)

    # ── 数据同步 ─────────────────────────────────────────────

    def _load_config(self) -> None:
        self._key_row.setText(api_config.api_key.value)
        self._cookie_row.setText(get_session_cookie())
        self._uid_edit.setText(get_user_id())

        idx = self._model_combo.findData(api_config.model_name.value)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        elif api_config.model_name.value:
            self._model_combo.setCurrentText(api_config.model_name.value)

        self._img_prefix_edit.setText(api_config.img_prefix.value)
        self._img_suffix_edit.setText(api_config.img_suffix.value)
        self._vid_prefix_edit.setText(api_config.vid_prefix.value)
        self._vid_suffix_edit.setText(api_config.vid_suffix.value)
        self._save_dir_edit.setText(get_img_save_dir())

    def _on_save(self) -> None:
        api_config.api_key.value = self._key_row.text().strip()
        set_session_cookie(self._cookie_row.text().strip())
        api_config.api_user_id.value = self._uid_edit.text().strip() or BJ_DEFAULT_UID

        model_data = self._model_combo.currentData()
        if model_data:
            api_config.model_name.value = model_data
        else:
            api_config.model_name.value = self._model_combo.currentText().strip()

        api_config.img_prefix.value = self._img_prefix_edit.text().strip()
        api_config.img_suffix.value = self._img_suffix_edit.text().strip()
        api_config.vid_prefix.value = self._vid_prefix_edit.text().strip()
        api_config.vid_suffix.value = self._vid_suffix_edit.text().strip()
        set_img_save_dir(self._save_dir_edit.text().strip())

        InfoBar.success(
            title="保存成功",
            content="API 配置已保存到本地，下次启动自动加载。",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self.window(),
        )

    # ── 交互逻辑 ─────────────────────────────────────────────

    def _on_browse_save_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择图片保存目录")
        if path:
            self._save_dir_edit.setText(path)

    def _on_fetch_cookie(self) -> None:
        from cookie_util import CookieLoginDialog
        dlg = CookieLoginDialog(self.window())
        dlg.cookie_obtained.connect(self._on_cookie_filled)
        dlg.exec()

    def _on_cookie_filled(self, session_cookie: str, user_id: str) -> None:
        if session_cookie:
            self._cookie_row.setText(session_cookie)
            set_session_cookie(session_cookie)
        if user_id:
            self._uid_edit.setText(user_id)
            set_user_id(user_id)

    def _on_test_connection(self) -> None:
        if self._test_thread and self._test_thread.isRunning():
            return
        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中...")
        self._status_label.setText("")

        config = {
            "session_cookie": self._cookie_row.text().strip(),
            "api_key": self._key_row.text().strip(),
            "user_id": self._uid_edit.text().strip(),
        }

        self._test_thread = ConnectionTestThread(config, self)
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, ok: bool, detail: str) -> None:
        self._test_btn.setEnabled(True)
        self._test_btn.setText("测试连接")
        if ok:
            self._status_label.setStyleSheet("color: #2ea043;")
        else:
            self._status_label.setStyleSheet("color: #f85149;")
        self._status_label.setText(detail)
