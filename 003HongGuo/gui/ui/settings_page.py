"""设置页 - 外观, 下载, 缓存, 行为"""
import logging
import shutil
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFileDialog
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (
    SettingCardGroup, ComboBoxSettingCard, SwitchSettingCard,
    PushSettingCard, PrimaryPushSettingCard,
    FluentIcon, setTheme, Theme, InfoBar, InfoBarPosition,
    ConfigItem,
)

from gui.widgets.series_info_widget import CACHE_DIR

logger = logging.getLogger("hongguo")

THEME_OPTIONS = ["Light", "Dark", "System"]
THEME_TEXTS = ["浅色", "深色", "跟随系统"]
THEME_MAP = {"Light": Theme.LIGHT, "Dark": Theme.DARK, "System": Theme.AUTO}

CLOSE_OPTIONS = ["exit", "tray"]
CLOSE_TEXTS = ["直接退出", "最小化到系统托盘"]


def _make_config_item(value, options: list):
    """创建一个简单的 ConfigItem 用于 ComboBoxSettingCard
    options: 内部选项值列表 (非显示文本)
    """
    item = ConfigItem("settings", "_temp", value)
    item.options = options
    return item


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    mica_changed = Signal(bool)
    download_path_changed = Signal(str)
    max_concurrent_changed = Signal(int)
    max_retries_changed = Signal(int)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)

        # === 外观 ===
        appearance_group = SettingCardGroup("外观")

        self._theme_card = ComboBoxSettingCard(
            configItem=_make_config_item(self.config.theme, THEME_OPTIONS),
            icon=FluentIcon.PALETTE,
            title="主题",
            content="选择应用程序主题",
            texts=THEME_TEXTS,
            parent=appearance_group,
        )
        self._theme_card.comboBox.currentIndexChanged.connect(
            lambda idx: self._on_theme_changed(THEME_OPTIONS[idx])
        )
        appearance_group.addSettingCard(self._theme_card)

        self._mica_card = SwitchSettingCard(
            icon=FluentIcon.TRANSPARENT,
            title="Mica 效果",
            content="启用 Windows 11 Mica 半透明背景 (需重启)",
            parent=appearance_group,
        )
        self._mica_card.checkedChanged.connect(self._on_mica_changed)
        self._mica_card.setChecked(self.config.mica_enabled)
        appearance_group.addSettingCard(self._mica_card)
        layout.addWidget(appearance_group)

        # === 下载 ===
        download_group = SettingCardGroup("下载")

        self._path_card = PushSettingCard(
            "更改目录",
            icon=FluentIcon.FOLDER,
            title="默认下载路径",
            content=self.config.download_path,
            parent=download_group,
        )
        self._path_card.clicked.connect(self._on_change_path)
        download_group.addSettingCard(self._path_card)

        self._concurrent_card = ComboBoxSettingCard(
            configItem=_make_config_item(str(self.config.max_concurrent), ["1","2","3","4","5"]),
            icon=FluentIcon.SPEED_HIGH,
            title="最大并发下载",
            content="同时下载的集数上限 (1-5)",
            texts=["1", "2", "3", "4", "5"],
            parent=download_group,
        )
        self._concurrent_card.comboBox.currentTextChanged.connect(self._on_concurrent_changed)
        download_group.addSettingCard(self._concurrent_card)

        self._retry_card = ComboBoxSettingCard(
            configItem=_make_config_item(str(self.config.max_retries), [str(i) for i in range(11)]),
            icon=FluentIcon.SYNC,
            title="最大重试次数",
            content="单个文件下载失败后的重试次数",
            texts=[str(i) for i in range(11)],
            parent=download_group,
        )
        self._retry_card.comboBox.currentTextChanged.connect(self._on_retries_changed)
        download_group.addSettingCard(self._retry_card)
        layout.addWidget(download_group)

        # === 缓存 ===
        cache_group = SettingCardGroup("缓存")
        cache_size = self._get_cache_size()
        self._cache_card = PrimaryPushSettingCard(
            "清除",
            icon=FluentIcon.DELETE,
            title="清除封面缓存",
            content=f"当前缓存大小: {self._format_size(cache_size)}",
            parent=cache_group,
        )
        self._cache_card.clicked.connect(self._on_clear_cache)
        cache_group.addSettingCard(self._cache_card)
        layout.addWidget(cache_group)

        # === 行为 ===
        behavior_group = SettingCardGroup("行为")
        self._close_card = ComboBoxSettingCard(
            configItem=_make_config_item(self.config.close_behavior, CLOSE_OPTIONS),
            icon=FluentIcon.CLOSE,
            title="关闭行为",
            content="点击窗口关闭按钮时的行为",
            texts=CLOSE_TEXTS,
            parent=behavior_group,
        )
        self._close_card.comboBox.currentIndexChanged.connect(
            lambda idx: self._on_close_behavior_changed(CLOSE_OPTIONS[idx])
        )
        behavior_group.addSettingCard(self._close_card)
        layout.addWidget(behavior_group)

        layout.addStretch()

    def _on_theme_changed(self, text: str):
        theme = THEME_MAP.get(text, Theme.LIGHT)
        setTheme(theme)
        self.config.theme = text
        self.theme_changed.emit(text)

    def _on_mica_changed(self, checked: bool):
        self.config.mica_enabled = checked
        self.mica_changed.emit(checked)

    def _on_change_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择下载目录", self.config.download_path)
        if path:
            self.config.download_path = path
            self._path_card.setContent(path)
            self.download_path_changed.emit(path)

    def _on_concurrent_changed(self, text: str):
        n = int(text)
        self.config.max_concurrent = n
        self.max_concurrent_changed.emit(n)

    def _on_retries_changed(self, text: str):
        n = int(text)
        self.config.max_retries = n
        self.max_retries_changed.emit(n)

    def _on_close_behavior_changed(self, text: str):
        self.config.close_behavior = text

    def _on_clear_cache(self):
        if not CACHE_DIR.exists() or not any(CACHE_DIR.iterdir()):
            InfoBar.info("缓存为空", "无需清理", parent=self)
            return
        # 确认
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("确认清除缓存")
        msg.setText("确定要清除所有封面缓存吗?")
        msg.setInformativeText("缓存文件将被移入回收站, 需要时可恢复。")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        if msg.exec() != QMessageBox.Ok:
            return

        try:
            from send2trash import send2trash
            for f in CACHE_DIR.iterdir():
                send2trash(str(f))
        except Exception as e:
            logger.warning(f"清除缓存失败: {e}")
            # 备用: 直接删除
            import shutil
            shutil.rmtree(CACHE_DIR, ignore_errors=True)
            CACHE_DIR.mkdir(exist_ok=True)

        self._cache_card.setContent("当前缓存大小: 0 B")
        InfoBar.success("缓存已清除", "文件已移入回收站", parent=self)

    def _get_cache_size(self) -> int:
        total = 0
        if CACHE_DIR.exists():
            for f in CACHE_DIR.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        return total

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / 1024 / 1024:.1f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.0f} KB"
        return f"{size_bytes} B"
