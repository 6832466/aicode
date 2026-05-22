"""主窗口 - 自定义固定侧边栏 + 折叠式分组"""
import os
import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QSystemTrayIcon, QFrame, QLabel,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QAction, QFont
from qfluentwidgets import (
    setTheme, Theme, InfoBar, InfoBarPosition, SystemTrayMenu,
    FluentIcon as FIF,
)

from app.core.settings_manager import SettingsManager
from app.core.task_manager import TaskManager
from app.pages.download_queue import DownloadQueuePage
from app.pages.completed import CompletedPage
from app.pages.settings_page import SettingsPage
from app.pages.logs_page import LogsPage
from app.widgets.sidebar import CustomSidebar


class MainWindow(QWidget):
    """主窗口 - 左侧固定卷帘侧边栏 + 右侧内容区"""

    def __init__(self):
        super().__init__()
        self.setObjectName('MainWindow')
        self.setWindowTitle('乐乐短视频下载器    微信：rpalele')
        self.resize(1150, 760)
        self.setMinimumSize(960, 620)

        self._init_managers()
        self._init_ui()
        self._init_tray()
        self._apply_theme()

        # 默认显示下载队列
        self._switch_page('download_queue')

    def _init_managers(self):
        settings_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'settings.json')
        self.settings = SettingsManager(os.path.normpath(settings_path))
        self.task_mgr = TaskManager(self.settings)

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 左侧边栏 ──
        self.sidebar = CustomSidebar()
        self.sidebar.page_changed.connect(self._switch_page)

        # 边栏与内容间的分割线
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setStyleSheet('border: none; background: #E5E5E5; max-width: 1px;')
        divider.setFixedWidth(1)

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(divider)

        # ── 右侧内容区 ──
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 顶部标题栏
        self._init_titlebar(right_layout)

        # 页面栈
        self.stack = QStackedWidget()
        self.stack.setStyleSheet('background: #FFFFFF;')

        # 创建所有页面
        self.download_page = DownloadQueuePage(self.task_mgr, self.settings, self)
        self.download_page.setObjectName('download_queue')
        self.completed_page = CompletedPage(self.settings, self)
        self.completed_page.setObjectName('completed')
        self.settings_page = SettingsPage(self.settings, parent=self)
        self.settings_page.setObjectName('settings')
        self.logs_page = LogsPage(parent=self)
        self.logs_page.setObjectName('logs')

        self.download_page.set_task_manager(self.task_mgr)
        self.completed_page.re_download_requested.connect(self.task_mgr.add_task)

        # 页面映射
        self._page_map = {
            'download_queue': self.download_page,
            'completed': self.completed_page,
            'settings': self.settings_page,
            'logs': self.logs_page,
        }

        for page in self._page_map.values():
            self.stack.addWidget(page)

        right_layout.addWidget(self.stack, stretch=1)
        main_layout.addWidget(right_container, stretch=1)

        self.setStyleSheet("""
            #MainWindow {
                background: #FFFFFF;
            }
        """)

    def _init_titlebar(self, parent_layout):
        """顶部标题栏 - 简洁风格"""
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet('background: #FFFFFF; border-bottom: 1px solid #E5E5E5;')

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 12, 0)

        title = QLabel('乐乐短视频下载器')
        title.setFont(QFont('Microsoft YaHei', 13, QFont.Bold))
        title.setStyleSheet('color: #1a1a1a; border: none;')
        layout.addWidget(title)

        layout.addStretch()
        parent_layout.addWidget(bar)

    def _switch_page(self, key: str):
        """切换页面"""
        if key in self._page_map:
            page = self._page_map[key]
            self.stack.setCurrentWidget(page)
            if hasattr(page, 'refresh'):
                page.refresh()

    def _init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        # 托盘图标使用 1.ico
        import sys
        def _tray_resource_path(relative_path):
            if getattr(sys, 'frozen', False):
                return os.path.join(sys._MEIPASS, relative_path)
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', relative_path)

        icon_path = _tray_resource_path('1.ico')
        if os.path.exists(icon_path):
            tray_icon = QIcon(icon_path)
        else:
            tray_icon = QIcon()
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(tray_icon)
        self.tray.setToolTip('乐乐短视频下载器')

        menu = SystemTrayMenu('乐乐短视频下载器', parent=self)
        show_act = QAction('显示主窗口', self)
        show_act.triggered.connect(self._show_window)
        menu.addAction(show_act)
        menu.addSeparator()
        quit_act = QAction('退出', self)
        quit_act.triggered.connect(self._quit_app)
        menu.addAction(quit_act)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._show_window()
            if r == QSystemTrayIcon.DoubleClick else None
        )
        self.tray.show()

    def _show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit_app(self):
        self.task_mgr.stop()
        self.settings.save()
        if hasattr(self, 'tray'):
            self.tray.hide()
        QApplication.quit()

    def _apply_theme(self):
        theme = self.settings.get('general.theme', 'auto')
        if theme == 'dark':
            setTheme(Theme.DARK)
        elif theme == 'light':
            setTheme(Theme.LIGHT)
        else:
            setTheme(Theme.AUTO)

    def closeEvent(self, event):
        minimize_to_tray = self.settings.get('general.minimize_to_tray', True)
        if minimize_to_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            self.task_mgr.stop()
            self.settings.save()
            if hasattr(self, 'tray'):
                self.tray.hide()
            super().closeEvent(event)
