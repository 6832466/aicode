from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from qfluentwidgets import FluentIcon, FluentWindow, NavigationItemPosition

from app.api_client import BitBrowserAPI
from app.config import app_icon_path, APP_NAME
from app.monitor import StatusMonitor
from ui.pages.settings_page import SettingsPage
from ui.pages.dashboard_page import DashboardPage
from ui.pages.group_page import GroupPage
from ui.pages.browser_page import BrowserPage

logger = logging.getLogger(__name__)


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(app_icon_path()))
        self.resize(1280, 800)

        # API 客户端（单例）
        self.api = BitBrowserAPI()

        # 状态监控
        self.monitor = StatusMonitor(self.api, self)
        self.monitor.alive_updated.connect(self._on_alive_updated)

        # 创建页面
        self.dashboard_page = DashboardPage(self.api, self)
        self.dashboard_page.setObjectName("dashboard")
        self.group_page = GroupPage(self.api, self)
        self.group_page.setObjectName("group")
        self.browser_page = BrowserPage(self.api, self)
        self.browser_page.setObjectName("browser")
        self.settings_page = SettingsPage(self.api, self)
        self.settings_page.setObjectName("settings")

        # 注册导航
        self.addSubInterface(self.dashboard_page, FluentIcon.HOME, "首页")
        self.addSubInterface(self.group_page, FluentIcon.TAG, "分组")
        self.addSubInterface(self.browser_page, FluentIcon.APPLICATION, "浏览器")
        self.addSubInterface(
            self.settings_page,
            FluentIcon.SETTING,
            "设置",
            NavigationItemPosition.BOTTOM,
        )

        # 设置页连接变化时通知其他页面
        self.settings_page.connection_changed.connect(self._on_connection_changed)

        # 从 QSettings 加载已保存的 URL
        self.settings_page.load_settings()

    def _on_connection_changed(self, connected: bool):
        self.dashboard_page.set_connected(connected)
        if connected:
            self.monitor.start()
            self.dashboard_page.refresh_data()
        else:
            self.monitor.stop()

    def _on_alive_updated(self, alive_ids: set[str]):
        """状态监控更新时刷新浏览器页面的状态灯"""
        self.browser_page.update_alive_status(alive_ids)
        self.dashboard_page.card_open.set_value(str(len(alive_ids)))
