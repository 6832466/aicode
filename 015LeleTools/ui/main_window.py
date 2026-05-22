"""
主窗口 — FluentWindow 导航框架
"""

from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
    InfoBar, InfoBarPosition,
)

from app.constants import (
    WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT, app_icon_path,
)
from ui.pages.home_page import HomePage
from ui.pages.text_rewrite_page import TextRewritePage
from ui.pages.ai_chat_page import AIChatPage
from ui.pages.settings_page import SettingsPage


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self._init_window()
        self._init_pages()
        self._init_navigation()

    def _init_window(self):
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _init_pages(self):
        self.home_page = HomePage(self)
        self.text_rewrite_page = TextRewritePage(self)
        self.ai_chat_page = AIChatPage(self)
        self.settings_page = SettingsPage(self)

    def _init_navigation(self):
        self.addSubInterface(
            self.home_page, FluentIcon.HOME, "首页",
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.text_rewrite_page, FluentIcon.EDIT, "AI改文",
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.ai_chat_page, FluentIcon.CHAT, "AI对话",
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.settings_page, FluentIcon.SETTING, "全局设置",
            NavigationItemPosition.BOTTOM,
        )

    # ═══════════════════════════════════════════
    #  InfoBar 快捷方法
    # ═══════════════════════════════════════════

    def show_success(self, title: str, content: str):
        InfoBar.success(
            title=title, content=content,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000, parent=self,
        )

    def show_error(self, title: str, content: str):
        InfoBar.error(
            title=title, content=content,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000, parent=self,
        )

    def show_warning(self, title: str, content: str):
        InfoBar.warning(
            title=title, content=content,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000, parent=self,
        )
