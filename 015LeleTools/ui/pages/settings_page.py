"""
全局设置 — API端点管理、系统代理、界面偏好
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QThread
from qfluentwidgets import (
    CardWidget, LineEdit, PushButton, PrimaryPushButton,
    ComboBox, EditableComboBox, SwitchButton,
    StrongBodyLabel, CaptionLabel, BodyLabel,
    InfoBar, InfoBarPosition,
)

from app.config_manager import ConfigManager
from core.api_client import APIClient, APIClientError


class TestConnectionWorker(QThread):
    """测试 API 连接的工作线程"""
    result_ready = Signal(bool, str)

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def run(self):
        client = APIClient(self.base_url, self.api_key, self.model)
        ok, msg = client.test_connection()
        self.result_ready.emit(ok, msg)


class FetchModelsWorker(QThread):
    """获取模型列表的工作线程"""
    result_ready = Signal(bool, list)

    def __init__(self, base_url: str, api_key: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key

    def run(self):
        try:
            client = APIClient(self.base_url, self.api_key, "")
            models = client.get_models()
            self.result_ready.emit(True, models)
        except APIClientError as e:
            self.result_ready.emit(False, [])


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_page")
        self._parent = parent
        self.config = ConfigManager()
        self._editing_endpoint_name: str | None = None
        self._init_ui()
        self._load_config()

    # ═══════════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════════

    def _init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(20)

        # 标题
        title = StrongBodyLabel("全局设置")
        title.setStyleSheet("font-size: 28px; color: #1a1a1a;")
        layout.addWidget(title)

        # ── API 配置卡片 ──
        layout.addWidget(self._build_api_card())

        # ── 系统设置卡片 ──
        layout.addWidget(self._build_system_card())

        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _build_api_card(self) -> CardWidget:
        card = CardWidget()
        card.setObjectName("api_settings_card")
        ly = QVBoxLayout(card)
        ly.setContentsMargins(24, 20, 24, 20)
        ly.setSpacing(16)

        header = StrongBodyLabel("API 配置")
        header.setStyleSheet("font-size: 18px;")
        ly.addWidget(header)

        # --- 端点选择器 ---
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.addWidget(CaptionLabel("API 名称:"))

        self.endpoint_combo = ComboBox()
        self.endpoint_combo.setMinimumWidth(160)
        self.endpoint_combo.currentIndexChanged.connect(self._on_endpoint_changed)
        row1.addWidget(self.endpoint_combo)

        self.btn_add = PushButton("添加")
        self.btn_add.clicked.connect(self._on_add_endpoint)
        row1.addWidget(self.btn_add)

        self.btn_edit = PushButton("编辑")
        self.btn_edit.clicked.connect(self._on_edit_endpoint)
        row1.addWidget(self.btn_edit)

        self.btn_delete = PushButton("删除")
        self.btn_delete.clicked.connect(self._on_delete_endpoint)
        row1.addWidget(self.btn_delete)

        row1.addStretch()
        ly.addLayout(row1)

        # --- Base URL ---
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(CaptionLabel("Base URL:"))
        self.url_input = LineEdit()
        self.url_input.setPlaceholderText("https://api.example.com/v1")
        row2.addWidget(self.url_input, 1)
        ly.addLayout(row2)

        # --- API Key ---
        row3 = QHBoxLayout()
        row3.setSpacing(12)
        row3.addWidget(CaptionLabel("API Key:"))
        self.key_input = LineEdit()
        self.key_input.setPlaceholderText("sk-...")
        self.key_input.setEchoMode(LineEdit.EchoMode.Password)
        row3.addWidget(self.key_input, 1)

        self.btn_key_vis = PushButton("显示")
        self.btn_key_vis.clicked.connect(self._toggle_key_visibility)
        row3.addWidget(self.btn_key_vis)

        self.btn_copy_key = PushButton("复制")
        self.btn_copy_key.clicked.connect(self._copy_key)
        row3.addWidget(self.btn_copy_key)
        ly.addLayout(row3)

        # --- 模型选择 ---
        row4 = QHBoxLayout()
        row4.setSpacing(12)
        row4.addWidget(CaptionLabel("默认模型:"))
        self.model_combo = EditableComboBox()
        self.model_combo.setMinimumWidth(200)
        row4.addWidget(self.model_combo, 1)

        self.btn_fetch_models = PushButton("获取模型")
        self.btn_fetch_models.clicked.connect(self._on_fetch_models)
        row4.addWidget(self.btn_fetch_models)
        ly.addLayout(row4)

        # --- 操作按钮 ---
        row5 = QHBoxLayout()
        row5.setSpacing(12)

        self.btn_test = PrimaryPushButton("测试连接")
        self.btn_test.clicked.connect(self._on_test_connection)
        row5.addWidget(self.btn_test)

        self.btn_save_api = PushButton("保存")
        self.btn_save_api.clicked.connect(self._on_save_endpoint)
        row5.addWidget(self.btn_save_api)

        self.test_status = BodyLabel("")
        self.test_status.setStyleSheet("color: #888;")
        row5.addWidget(self.test_status, 1)
        ly.addLayout(row5)

        return card

    def _build_system_card(self) -> CardWidget:
        card = CardWidget()
        ly = QVBoxLayout(card)
        ly.setContentsMargins(24, 20, 24, 20)
        ly.setSpacing(16)

        header = StrongBodyLabel("系统设置")
        header.setStyleSheet("font-size: 18px;")
        ly.addWidget(header)

        # 代理开关
        row1 = QHBoxLayout()
        row1.addWidget(CaptionLabel("启用系统代理:"))
        self.proxy_switch = SwitchButton()
        self.proxy_switch.checkedChanged.connect(
            lambda v: self.config.set("proxy", "enabled", v)
        )
        row1.addWidget(self.proxy_switch)
        row1.addStretch()
        ly.addLayout(row1)

        # 超时设置
        row2 = QHBoxLayout()
        row2.addWidget(CaptionLabel("超时时间(秒):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 600)
        self.timeout_spin.setValue(60)
        self.timeout_spin.setFixedWidth(80)
        self.timeout_spin.valueChanged.connect(
            lambda v: self.config.set("api", "timeout", v)
        )
        row2.addWidget(self.timeout_spin)
        row2.addStretch()
        ly.addLayout(row2)

        # 自动保存记录
        row3 = QHBoxLayout()
        row3.addWidget(CaptionLabel("自动保存记录:"))
        self.autosave_switch = SwitchButton()
        self.autosave_switch.checkedChanged.connect(
            lambda v: self.config.set("api", "auto_save_records", v)
        )
        row3.addWidget(self.autosave_switch)
        row3.addStretch()
        ly.addLayout(row3)

        return card

    # ═══════════════════════════════════════════
    #  配置加载 / 同步
    # ═══════════════════════════════════════════

    def _load_config(self):
        """从配置文件加载 UI 状态"""
        # 端点列表
        self.endpoint_combo.clear()
        endpoints = self.config.get_endpoints()
        for ep in endpoints:
            self.endpoint_combo.addItem(ep.name)
        if endpoints:
            idx = 0
            default_name = self.config._data["api"]["default_endpoint"]
            if default_name:
                for i, ep in enumerate(endpoints):
                    if ep.name == default_name:
                        idx = i
                        break
            self.endpoint_combo.setCurrentIndex(idx)
            self._fill_endpoint_form(endpoints[idx])
        else:
            self._clear_endpoint_form()

        # 系统设置
        self.proxy_switch.setChecked(self.config.proxy_enabled)
        self.timeout_spin.setValue(self.config.timeout)
        self.autosave_switch.setChecked(self.config.auto_save_records)

    def _fill_endpoint_form(self, ep):
        """填充端点表单"""
        self._editing_endpoint_name = ep.name
        self.url_input.setText(ep.base_url)
        self.key_input.setText(ep.api_key)

        self.model_combo.clear()
        if ep.model:
            self.model_combo.addItem(ep.model)
            self.model_combo.setCurrentText(ep.model)

        self.test_status.setText("")

    def _clear_endpoint_form(self):
        """清空端点表单"""
        self._editing_endpoint_name = None
        self.url_input.clear()
        self.key_input.clear()
        self.model_combo.clear()
        self.test_status.setText("")

    # ═══════════════════════════════════════════
    #  端点管理槽函数
    # ═══════════════════════════════════════════

    def _on_endpoint_changed(self, idx: int):
        if idx < 0:
            return
        name = self.endpoint_combo.currentText()
        ep = self.config.get_endpoint(name)
        if ep:
            self._fill_endpoint_form(ep)
            self.config.set_default_endpoint(name)

    def _on_add_endpoint(self):
        """新增端点"""
        self._clear_endpoint_form()
        self.url_input.setPlaceholderText("https://api.example.com/v1")
        self.key_input.setPlaceholderText("sk-...")
        self.model_combo.clear()
        self.model_combo.setPlaceholderText("输入新端点名称后保存")
        self._editing_endpoint_name = None
        self.url_input.setFocus()
        self.test_status.setText("请在 Base URL 处输入新端点名称...")

    def _on_edit_endpoint(self):
        """编辑当前端点 — 实际上就是允许修改后保存"""
        self.test_status.setText("修改后请点击「保存」")

    def _on_delete_endpoint(self):
        name = self.endpoint_combo.currentText()
        if not name:
            return
        self.config.delete_endpoint(name)
        self._load_config()
        if self._parent:
            self._parent.show_success("已删除", f"端点「{name}」已删除")

    def _on_save_endpoint(self):
        """保存当前端点"""
        from models.config_model import APIEndpoint

        # 端点名称 — 优先用已有名称，否则从 URL 或用户输入获取
        name = self._editing_endpoint_name
        if not name:
            name = self.url_input.text().strip().rstrip("/").split("/")[-1]
            if not name:
                name = "未命名端点"
            if self.config.get_endpoint(name):
                self._show_error("端点名称重复，请修改后重试")
                return

        url = self.url_input.text().strip()
        key = self.key_input.text().strip()
        model = self.model_combo.currentText().strip()

        ep = APIEndpoint(name=name, base_url=url, api_key=key, model=model)
        self.config.add_or_update_endpoint(ep)

        self._load_config()
        # 选中刚保存的端点
        idx = self.endpoint_combo.findText(name)
        if idx >= 0:
            self.endpoint_combo.setCurrentIndex(idx)

        if self._parent:
            self._parent.show_success("已保存", f"端点「{name}」已保存")

    def _on_test_connection(self):
        """测试 API 连接"""
        url = self.url_input.text().strip()
        key = self.key_input.text().strip()
        model = self.model_combo.currentText().strip()

        if not url:
            self.test_status.setText("请先输入 Base URL")
            self.test_status.setStyleSheet("color: red;")
            return

        self.test_status.setText("正在测试连接...")
        self.test_status.setStyleSheet("color: #888;")
        self.btn_test.setEnabled(False)

        self._test_worker = TestConnectionWorker(url, key, model)
        self._test_worker.result_ready.connect(self._on_test_result)
        self._test_worker.start()

    def _on_test_result(self, ok: bool, msg: str):
        self.btn_test.setEnabled(True)
        if ok:
            self.test_status.setText(msg)
            self.test_status.setStyleSheet("color: green;")
        else:
            self.test_status.setText(msg)
            self.test_status.setStyleSheet("color: red;")

    def _on_fetch_models(self):
        """获取模型列表"""
        url = self.url_input.text().strip()
        key = self.key_input.text().strip()

        if not url:
            self.test_status.setText("请先输入 Base URL")
            self.test_status.setStyleSheet("color: red;")
            return

        self.test_status.setText("正在获取模型列表...")
        self.test_status.setStyleSheet("color: #888;")

        self._fetch_worker = FetchModelsWorker(url, key)
        self._fetch_worker.result_ready.connect(self._on_models_result)
        self._fetch_worker.start()

    def _on_models_result(self, ok: bool, models: list):
        if ok and models:
            self.model_combo.clear()
            self.model_combo.addItems(models)
            self.test_status.setText(f"获取到 {len(models)} 个模型")
            self.test_status.setStyleSheet("color: green;")
        else:
            self.test_status.setText("获取模型列表失败")
            self.test_status.setStyleSheet("color: red;")

    # ═══════════════════════════════════════════
    #  辅助
    # ═══════════════════════════════════════════

    def _toggle_key_visibility(self):
        if self.key_input.echoMode() == LineEdit.EchoMode.Password:
            self.key_input.setEchoMode(LineEdit.EchoMode.Normal)
            self.btn_key_vis.setText("隐藏")
        else:
            self.key_input.setEchoMode(LineEdit.EchoMode.Password)
            self.btn_key_vis.setText("显示")

    def _copy_key(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.key_input.text())
        if self._parent:
            self._parent.show_success("已复制", "API Key 已复制到剪贴板")

    def _show_error(self, msg: str):
        InfoBar.error(
            title="错误", content=msg,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000, parent=self,
        )

