import asyncio
import json
import logging
from pathlib import Path
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import QHeaderView, QTableView, QFileDialog, QMessageBox
from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, StrongBodyLabel,
    PushButton, LineEdit, ComboBox, SpinBox,
    InfoBar, InfoBarPosition, MessageBoxBase, SubtitleLabel,
    TableWidget, TogglePushButton,
)

from app.config import (
    settings_scope, SETTINGS_KEY_THEME, SETTINGS_KEY_REFRESH_INTERVAL,
    SETTINGS_KEY_PROXY_HTTP, SETTINGS_KEY_PROXY_HTTPS, SETTINGS_KEY_NOTIFY_THRESHOLD,
    SETTINGS_KEY_NOTIFY_ENABLED,
    api_keys_path, encrypt_api_key, decrypt_api_key,
)
from app.models import ApiKeyEntry
from app.modelscope_client import get_client
from ui.widgets.log_widget import LogWidget

logger = logging.getLogger(__name__)


class ApiKeysTableModel(QAbstractTableModel):
    HEADERS = ["激活", "名称", "API Key", "状态"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[ApiKeyEntry] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None

        entry = self._data[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 1:
                return entry.name
            elif col == 2:
                # Mask the key
                return "••••••••••••" if entry.encrypted_key else "未设置"
            elif col == 3:
                return "当前使用" if entry.active else ""

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or index.row() >= len(self._data):
            return False

        if role == Qt.CheckStateRole and index.column() == 0:
            # Only one active at a time
            for i, entry in enumerate(self._data):
                entry.active = (i == index.row())
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._data) - 1, 3))
            return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            flags |= Qt.ItemIsUserCheckable
        return flags

    def set_data(self, data: list[ApiKeyEntry]):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def get_entry(self, row: int) -> ApiKeyEntry | None:
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def add_entry(self, entry: ApiKeyEntry):
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append(entry)
        self.endInsertRows()

    def remove_entry(self, row: int):
        if 0 <= row < len(self._data):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._data.pop(row)
            self.endRemoveRows()

    def get_all(self) -> list[ApiKeyEntry]:
        return self._data.copy()

    def get_active_key(self) -> str | None:
        for entry in self._data:
            if entry.active and entry.encrypted_key:
                return decrypt_api_key(entry.encrypted_key)
        return None


class AddKeyDialog(MessageBoxBase):
    def __init__(self, parent=None, edit_entry: ApiKeyEntry = None):
        self._edit_entry = edit_entry
        super().__init__(parent)
        self._init_ui()
        if edit_entry:
            self._name_edit.setText(edit_entry.name)

    def _init_ui(self):
        from PySide6.QtWidgets import QVBoxLayout, QGridLayout

        layout = QVBoxLayout(self.widget)
        layout.setSpacing(12)

        title = "编辑 Key" if self._edit_entry else "添加 API Key"
        layout.addWidget(SubtitleLabel(title, self))

        form = QGridLayout()
        form.setSpacing(8)

        form.addWidget(BodyLabel("名称:"), 0, 0)
        self._name_edit = LineEdit()
        self._name_edit.setPlaceholderText("如：主账号、测试账号")
        form.addWidget(self._name_edit, 0, 1)

        form.addWidget(BodyLabel("API Key:"), 1, 0)
        self._key_edit = LineEdit()
        self._key_edit.setPlaceholderText("ms-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        self._key_edit.setEchoMode(LineEdit.Password)
        form.addWidget(self._key_edit, 1, 1)

        layout.addLayout(form)

    def get_entry(self) -> ApiKeyEntry | None:
        name = self._name_edit.text().strip()
        key = self._key_edit.text().strip()
        if not name:
            return None
        encrypted = encrypt_api_key(key) if key else ""
        return ApiKeyEntry(name=name, encrypted_key=encrypted, active=False)


class SettingsPage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._init_ui()
        self._load_settings()
        self._load_api_keys()

    def _init_ui(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout

        container = QWidget()
        self.setWidget(container)
        self.setWidgetResizable(True)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("设置"))
        header.addStretch()
        layout.addLayout(header)

        # API Keys Management
        keys_card = CardWidget()
        keys_layout = QVBoxLayout(keys_card)
        keys_layout.setContentsMargins(16, 16, 16, 16)
        keys_layout.setSpacing(12)

        keys_header = QHBoxLayout()
        keys_header.addWidget(StrongBodyLabel("API Key 管理"))
        keys_header.addStretch()

        self._btn_add_key = PushButton("添加")
        self._btn_add_key.setFixedWidth(60)
        self._btn_add_key.clicked.connect(self._add_api_key)
        keys_header.addWidget(self._btn_add_key)

        self._btn_edit_key = PushButton("编辑")
        self._btn_edit_key.setFixedWidth(60)
        self._btn_edit_key.clicked.connect(self._edit_api_key)
        keys_header.addWidget(self._btn_edit_key)

        self._btn_delete_key = PushButton("删除")
        self._btn_delete_key.setFixedWidth(60)
        self._btn_delete_key.clicked.connect(self._delete_api_key)
        keys_header.addWidget(self._btn_delete_key)

        keys_layout.addLayout(keys_header)

        self._keys_table = QTableView()
        self._keys_model = ApiKeysTableModel()
        self._keys_table.setModel(self._keys_model)
        self._keys_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._keys_table.setMaximumHeight(200)
        self._keys_table.setAlternatingRowColors(True)
        self._keys_table.clicked.connect(self._on_key_clicked)
        keys_layout.addWidget(self._keys_table)

        layout.addWidget(keys_card)

        # Proxy Settings
        proxy_card = CardWidget()
        proxy_layout = QGridLayout(proxy_card)
        proxy_layout.setContentsMargins(16, 16, 16, 16)
        proxy_layout.setVerticalSpacing(12)

        proxy_layout.addWidget(StrongBodyLabel("代理设置"), 0, 0, 1, 3)

        proxy_layout.addWidget(BodyLabel("HTTP 代理:"), 1, 0)
        self._proxy_http_edit = LineEdit()
        self._proxy_http_edit.setPlaceholderText("http://127.0.0.1:7890")
        self._proxy_http_edit.setFixedWidth(300)
        proxy_layout.addWidget(self._proxy_http_edit, 1, 1)

        self._btn_test_proxy = PushButton("测试连接")
        self._btn_test_proxy.setFixedWidth(80)
        self._btn_test_proxy.clicked.connect(self._test_proxy)
        proxy_layout.addWidget(self._btn_test_proxy, 1, 2)

        proxy_layout.addWidget(BodyLabel("HTTPS 代理:"), 2, 0)
        self._proxy_https_edit = LineEdit()
        self._proxy_https_edit.setPlaceholderText("http://127.0.0.1:7890")
        self._proxy_https_edit.setFixedWidth(300)
        proxy_layout.addWidget(self._proxy_https_edit, 2, 1)

        layout.addWidget(proxy_card)

        # Theme Settings
        theme_card = CardWidget()
        theme_layout = QGridLayout(theme_card)
        theme_layout.setContentsMargins(16, 16, 16, 16)
        theme_layout.setVerticalSpacing(12)

        theme_layout.addWidget(StrongBodyLabel("界面设置"), 0, 0, 1, 2)

        theme_layout.addWidget(BodyLabel("主题模式:"), 1, 0)
        self._theme_combo = ComboBox()
        self._theme_combo.addItems(["跟随系统", "浅色模式", "深色模式"])
        self._theme_combo.setFixedWidth(150)
        theme_layout.addWidget(self._theme_combo, 1, 1)

        theme_layout.addWidget(BodyLabel("刷新间隔:"), 2, 0)
        self._refresh_spin = SpinBox()
        self._refresh_spin.setRange(1, 60)
        self._refresh_spin.setValue(5)
        self._refresh_spin.setSuffix(" 分钟")
        self._refresh_spin.setFixedWidth(150)
        theme_layout.addWidget(self._refresh_spin, 2, 1)

        layout.addWidget(theme_card)

        # Notification Settings
        notify_card = CardWidget()
        notify_layout = QGridLayout(notify_card)
        notify_layout.setContentsMargins(16, 16, 16, 16)
        notify_layout.setVerticalSpacing(12)

        notify_layout.addWidget(StrongBodyLabel("通知设置"), 0, 0, 1, 2)

        notify_layout.addWidget(BodyLabel("启用通知:"), 1, 0)
        self._notify_toggle = TogglePushButton()
        self._notify_toggle.setFixedWidth(120)
        notify_layout.addWidget(self._notify_toggle, 1, 1)
        notify_layout.addWidget(BodyLabel("开启后额度紧张时发送桌面通知"), 1, 2)

        notify_layout.addWidget(BodyLabel("预警阈值:"), 2, 0)
        self._threshold_spin = SpinBox()
        self._threshold_spin.setRange(5, 50)
        self._threshold_spin.setValue(20)
        self._threshold_spin.setSuffix("%")
        self._threshold_spin.setFixedWidth(150)
        notify_layout.addWidget(self._threshold_spin, 2, 1)
        notify_layout.addWidget(BodyLabel("当额度低于此阈值时发送通知"), 2, 2)

        layout.addWidget(notify_card)

        # Save Button
        save_layout = QHBoxLayout()
        save_layout.addStretch()

        self._btn_save = PushButton("保存设置")
        self._btn_save.setFixedWidth(100)
        self._btn_save.clicked.connect(self._save_settings)
        save_layout.addWidget(self._btn_save)

        layout.addLayout(save_layout)

        # Log
        self._log_widget = LogWidget()
        layout.addWidget(self._log_widget)

    def _load_settings(self):
        s = settings_scope()
        self._theme_combo.setCurrentIndex(int(s.value(SETTINGS_KEY_THEME, 0)))
        self._refresh_spin.setValue(int(s.value(SETTINGS_KEY_REFRESH_INTERVAL, 5)))
        self._proxy_http_edit.setText(s.value(SETTINGS_KEY_PROXY_HTTP, ""))
        self._proxy_https_edit.setText(s.value(SETTINGS_KEY_PROXY_HTTPS, ""))
        self._threshold_spin.setValue(int(s.value(SETTINGS_KEY_NOTIFY_THRESHOLD, 20)))
        notify_enabled = s.value(SETTINGS_KEY_NOTIFY_ENABLED, "true").lower() != "false"
        self._notify_toggle.setChecked(notify_enabled)

    def _load_api_keys(self):
        path = api_keys_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entries = [ApiKeyEntry.from_dict(d) for d in data]
                self._keys_model.set_data(entries)
                self._log_widget.info(f"已加载 {len(entries)} 个 API Key")
            except Exception as e:
                logger.warning(f"Failed to load API keys: {e}")
                self._keys_model.set_data([])

    def _save_api_keys(self):
        path = api_keys_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = self._keys_model.get_all()
        data = [e.to_dict() for e in entries]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _add_api_key(self):
        dlg = AddKeyDialog(self)
        if dlg.exec():
            entry = dlg.get_entry()
            if entry:
                self._keys_model.add_entry(entry)
                self._save_api_keys()
                self._log_widget.info(f"已添加 API Key: {entry.name}")

    def _edit_api_key(self):
        rows = self._keys_table.selectedIndexes()
        if not rows:
            InfoBar.warning("请先选择一个 Key", parent=self)
            return
        row = rows[0].row()
        entry = self._keys_model.get_entry(row)
        if entry:
            dlg = AddKeyDialog(self, edit_entry=entry)
            if dlg.exec():
                new_entry = dlg.get_entry()
                if new_entry:
                    # Preserve active state
                    new_entry.active = entry.active
                    self._keys_model.remove_entry(row)
                    self._keys_model.add_entry(new_entry)
                    self._save_api_keys()
                    self._log_widget.info(f"已更新 API Key: {new_entry.name}")

    def _delete_api_key(self):
        rows = self._keys_table.selectedIndexes()
        if not rows:
            InfoBar.warning("请先选择一个 Key", parent=self)
            return
        row = rows[0].row()
        entry = self._keys_model.get_entry(row)
        if entry:
            btn = QMessageBox.question(
                self, "确认删除",
                f"确定要删除 '{entry.name}' 吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if btn == QMessageBox.Yes:
                self._keys_model.remove_entry(row)
                self._save_api_keys()
                self._log_widget.info(f"已删除 API Key: {entry.name}")

    def _on_key_clicked(self, index):
        if index.column() == 0:  # Activate checkbox
            entry = self._keys_model.get_entry(index.row())
            if entry:
                entry.active = True
                # Deactivate others
                for i, e in enumerate(self._keys_model.get_all()):
                    e.active = (i == index.row())
                self._keys_model.dataChanged.emit(
                    self._keys_model.index(0, 0),
                    self._keys_model.index(len(self._keys_model.get_all()) - 1, 3)
                )
                self._save_api_keys()
                # Apply the key
                active_key = self._keys_model.get_active_key()
                if active_key:
                    client = get_client()
                    proxy = self._proxy_http_edit.text().strip() or self._proxy_https_edit.text().strip()
                    client.configure(active_key, proxy if proxy else None)
                    self._log_widget.info(f"已切换到: {entry.name}")
                self._save_settings()

    def _test_proxy(self):
        proxy = self._proxy_http_edit.text().strip() or self._proxy_https_edit.text().strip()
        if not proxy:
            InfoBar.warning("请先配置代理", parent=self)
            return

        self._btn_test_proxy.setEnabled(False)
        self._btn_test_proxy.setText("测试中...")

        async def _test():
            import aiohttp
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.head(
                        "https://api-inference.modelscope.cn/v1/models",
                        proxy=proxy
                    ) as resp:
                        if resp.status < 500:
                            InfoBar.success("连接成功", f"代理可用，状态码: {resp.status}", parent=self)
                            self._log_widget.info(f"代理测试成功: {proxy}")
                        else:
                            InfoBar.error("连接失败", f"服务器返回: {resp.status}", parent=self)
                            self._log_widget.error(f"代理测试失败: HTTP {resp.status}")
            except Exception as e:
                InfoBar.error("连接失败", str(e), parent=self)
                self._log_widget.error(f"代理测试失败: {e}")
            finally:
                self._btn_test_proxy.setEnabled(True)
                self._btn_test_proxy.setText("测试连接")

        asyncio.ensure_future(_test())

    def _save_settings(self):
        s = settings_scope()
        s.setValue(SETTINGS_KEY_THEME, self._theme_combo.currentIndex())
        s.setValue(SETTINGS_KEY_REFRESH_INTERVAL, self._refresh_spin.value())
        s.setValue(SETTINGS_KEY_PROXY_HTTP, self._proxy_http_edit.text())
        s.setValue(SETTINGS_KEY_PROXY_HTTPS, self._proxy_https_edit.text())
        s.setValue(SETTINGS_KEY_NOTIFY_THRESHOLD, self._threshold_spin.value())
        s.setValue(SETTINGS_KEY_NOTIFY_ENABLED, "true" if self._notify_toggle.isChecked() else "false")

        # Apply active API key
        active_key = self._keys_model.get_active_key()
        if active_key:
            proxy = self._proxy_http_edit.text().strip() or self._proxy_https_edit.text().strip()
            get_client().configure(active_key, proxy if proxy else None)

        # Apply theme
        from app.config import apply_theme
        apply_theme(self._theme_combo.currentIndex())

        InfoBar.success("保存成功", "设置已保存", position=InfoBarPosition.TOP, parent=self)
        self._log_widget.info("设置已保存")

        # Notify parent to apply config
        main_window = self.parent().parent() if self.parent() else None
        if main_window and hasattr(main_window, "apply_config"):
            main_window.apply_config()

    def get_active_api_key(self) -> str | None:
        """Public method to get the currently active API key."""
        return self._keys_model.get_active_key()
