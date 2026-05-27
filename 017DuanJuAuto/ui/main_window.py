"""主窗口 —— FluentWindow 侧边栏导航。"""
from pathlib import Path

from PySide6.QtGui import QIcon

from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
)

from ui.scrape_page import ScrapePage
from ui.settings_page import SettingsPage

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_ICON = PROJECT_ROOT / "1.ico"


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("短剧素材采集工具")
        if APP_ICON.exists():
            self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1100, 750)

        self._scrape_page = ScrapePage(self)
        self._settings_page = SettingsPage(self)

        self.addSubInterface(
            self._scrape_page, FluentIcon.CLOUD, "素材采集",
            position=NavigationItemPosition.SCROLL,
        )
        self.addSubInterface(
            self._settings_page, FluentIcon.SETTING, "设置",
            position=NavigationItemPosition.BOTTOM,
        )

    def closeEvent(self, event):
        self._scrape_page.cleanup()
        event.accept()
