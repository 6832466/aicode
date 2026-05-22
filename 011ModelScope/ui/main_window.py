import logging
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from qfluentwidgets import FluentWindow, FluentIcon, NavigationItemPosition

from app.config import app_icon_path, settings_scope, SETTINGS_KEY_API_KEY
from app.modelscope_client import get_client
from ui.pages.quota_page import QuotaPage
from ui.pages.models_page import ModelsPage
from ui.pages.chat_page import ChatPage
from ui.pages.image_page import ImagePage
from ui.pages.batch_page import BatchPage
from ui.pages.tools_page import ToolsPage
from ui.pages.settings_page import SettingsPage

logger = logging.getLogger(__name__)


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("魔塔管理器    微信：rpalele")
        self.resize(1280, 800)
        self._set_app_icon()
        self._init_tray()

        self.client = get_client()
        self._init_pages()
        self._init_navigation()

    def _set_app_icon(self):
        p = app_icon_path()
        if p.exists():
            icon = QIcon(str(p))
            self.setWindowIcon(icon)
            QApplication.instance().setWindowIcon(icon)

    def _init_tray(self):
        """Initialize system tray icon."""
        p = app_icon_path()
        if p.exists():
            tray_icon = QIcon(str(p))
            self._tray = QSystemTrayIcon(tray_icon, self)
            self._tray.setToolTip("魔塔管理器")

            # Tray menu
            tray_menu = QMenu()
            show_action = tray_menu.addAction("显示窗口")
            show_action.triggered.connect(self.show)
            quit_action = tray_menu.addAction("退出")
            quit_action.triggered.connect(self._quit_app)
            self._tray.setContextMenu(tray_menu)
            self._tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()

    def _quit_app(self):
        QApplication.instance().quit()

    def closeEvent(self, event):
        """Override close event to minimize to tray."""
        # Minimize to tray instead of closing
        event.ignore()
        self.hide()
        self._tray.showMessage("魔塔管理器", "已最小化到系统托盘", QSystemTrayIcon.Information, 2000)

    def _init_pages(self):
        self.quota_page = QuotaPage(self)
        self.models_page = ModelsPage(self)
        self.chat_page = ChatPage(self)
        self.image_page = ImagePage(self)
        self.batch_page = BatchPage(self)
        self.tools_page = ToolsPage(self)
        self.settings_page = SettingsPage(self)

    def _init_navigation(self):
        self.addSubInterface(
            self.quota_page, FluentIcon.COMPLETED, "额度概览",
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.models_page, FluentIcon.TAG, "模型管理",
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.chat_page, FluentIcon.CHAT, "对话中心",
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.image_page, FluentIcon.PHOTO, "文生图",
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.batch_page, FluentIcon.SYNC, "批量任务",
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.tools_page, FluentIcon.DEVELOPER_TOOLS, "辅助工具",
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.settings_page, FluentIcon.SETTING, "设置",
            position=NavigationItemPosition.BOTTOM,
        )

    def load_config(self):
        """Load configuration from settings."""
        # Apply theme
        from app.config import SETTINGS_KEY_THEME, apply_theme
        s = settings_scope()
        theme_idx = int(s.value(SETTINGS_KEY_THEME, 0))
        apply_theme(theme_idx)

        # Load from new multi-key system
        active_key = self.settings_page.get_active_api_key()
        if active_key:
            self.client.configure(active_key)
            logger.info("API Key loaded from settings")
        else:
            # Fallback to legacy single key
            api_key = s.value(SETTINGS_KEY_API_KEY, "")
            if api_key:
                self.client.configure(api_key)
                logger.info("API Key loaded from legacy settings")

        # Validate API key on startup (deferred so UI is shown first)
        self._validate_key_on_startup()

    def _validate_key_on_startup(self):
        """Validate API key asynchronously after UI is ready."""
        import asyncio
        from PySide6.QtCore import QTimer
        from qfluentwidgets import InfoBar, InfoBarPosition

        async def _validate():
            if not self.client._api_key:
                QTimer.singleShot(0, lambda: InfoBar.warning(
                    "未配置 API Key",
                    "请在设置中添加魔塔社区 API Key",
                    duration=8000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                ))
                return
            try:
                valid = await self.client.validate_api_key()
                if not valid:
                    QTimer.singleShot(0, lambda: InfoBar.error(
                        "API Key 无效",
                        "请检查设置中的 API Key 是否正确",
                        duration=8000,
                        position=InfoBarPosition.TOP,
                        parent=self,
                    ))
                else:
                    logger.info("API Key 验证通过")
            except Exception as e:
                logger.warning(f"API Key 验证失败: {e}")

        QTimer.singleShot(1000, lambda: asyncio.ensure_future(_validate()))

    def apply_config(self):
        """Apply settings changes."""
        self.load_config()
        self.quota_page.refresh_quota()
