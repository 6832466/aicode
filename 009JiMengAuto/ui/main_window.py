"""主窗口 - 即梦AI视频批量生成管理工具"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget, QVBoxLayout
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    InfoBar, InfoBarPosition,
)

from ui.task_page import TaskPage
from ui.download_page import DownloadPage
from ui.settings_page import SettingsPage
from core.dreamina_cli import DreaminaCLI
from core.task_manager import TaskManager
from core.download_manager import DownloadManager
from core.material_matcher import MaterialMatcher
from config.settings_manager import get_config
from utils.theme import THEME


class MainWindow(FluentWindow):
    """应用主窗口"""

    def __init__(self, task_manager: TaskManager,
                 download_manager: DownloadManager,
                 material_matcher: MaterialMatcher,
                 dreamina_cli: DreaminaCLI,
                 parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.download_manager = download_manager
        self.material_matcher = material_matcher
        self.dreamina_cli = dreamina_cli
        self.config = get_config()

        self._init_window()
        self._init_pages()
        self._init_status_bar()
        self._check_cli()

    def _init_window(self):
        """初始化窗口"""
        self.setWindowTitle("即梦AI视频批量生成")
        self.setWindowIcon(QIcon(str(self._icon_path())))
        self.resize(1280, 800)
        self.setMinimumSize(1024, 600)

        # 应用深色主题
        self.setStyleSheet(f"""
            FluentWindow {{
                background-color: {THEME['bg_dark']};
            }}
        """)

    def _icon_path(self):
        """获取图标路径"""
        import sys
        from pathlib import Path
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
            for p in [base / "1.ico", base / "_internal" / "1.ico"]:
                if p.exists():
                    return str(p)
        return str(Path(__file__).resolve().parent.parent / "1.ico")

    def _init_pages(self):
        """初始化页面"""
        # 任务管理页
        self.task_page = TaskPage(
            self.task_manager, self.material_matcher, self.dreamina_cli, self
        )
        self.task_page.setObjectName("task_page")

        # 下载管理页
        self.download_page = DownloadPage(self.download_manager, self)
        self.download_page.setObjectName("download_page")

        # 设置页
        self.settings_page = SettingsPage(self.config, self.material_matcher, self)
        self.settings_page.setObjectName("settings_page")

        # 添加导航项
        self.addSubInterface(self.task_page, FluentIcon.VIDEO, "任务管理")
        self.addSubInterface(self.download_page, FluentIcon.DOWNLOAD, "下载管理")
        self.addSubInterface(self.settings_page, FluentIcon.SETTING, "设置",
                             NavigationItemPosition.BOTTOM)

        # 连接生成完成 → 添加下载
        self.task_manager.task_updated.connect(self._on_task_updated)

    def _init_status_bar(self):
        """自定义状态栏"""
        # 状态信息
        self._status_label = QLabel()
        self._status_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 12px;")
        self._cli_status_label = QLabel()
        self._cli_status_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 12px;")
        self._update_status()

        # FluentWindow 没有 statusBar，使用 bottomBar
        # 直接在 titleBar 右侧显示状态
        # 定时刷新状态
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(5000)

        # 连接信号更新
        self.task_manager.task_added.connect(lambda _: self._update_status())
        self.task_manager.task_removed.connect(lambda _: self._update_status())
        self.task_manager.task_updated.connect(lambda _: self._update_status())

    def _update_status(self):
        """更新状态栏信息"""
        stats = self.task_manager.get_stats()
        total = sum(stats.values())
        completed = stats.get("completed", 0)
        pending = stats.get("pending", 0)
        self._status_label.setText(f"任务总数: {total} | 已完成: {completed} | 待生成: {pending}")

    def _check_cli(self):
        """检查 dreamina CLI 状态"""
        if self.config.auto_check_cli.value:
            ok = self.dreamina_cli.check_available()
            logged_in = self.dreamina_cli.check_login() if ok else False
            self._update_cli_status(ok, logged_in)

    def _update_cli_status(self, available: bool, logged_in: bool):
        """更新CLI状态显示"""
        if available and logged_in:
            self._cli_status_label.setText("● CLI 已登录")
            self._cli_status_label.setStyleSheet(f"color: {THEME['success']}; font-size: 12px;")
        elif available:
            self._cli_status_label.setText("○ CLI 未登录")
            self._cli_status_label.setStyleSheet(f"color: {THEME['warning']}; font-size: 12px;")
        else:
            self._cli_status_label.setText("✕ CLI 未安装")
            self._cli_status_label.setStyleSheet(f"color: {THEME['danger']}; font-size: 12px;")

    def _on_task_updated(self, task):
        """任务状态更新时，自动添加下载"""
        from data.models import TaskStatus
        if task.status == TaskStatus.COMPLETED and task.video_url:
            existing = [d for d in self.download_manager.get_all_downloads()
                        if d.task_id == task.id]
            if not existing:
                self.download_manager.add_download(
                    url=task.video_url,
                    scene=task.scene,
                    task_id=task.id,
                )

    def show_cli_login(self):
        """显示 CLI 登录提示"""
        InfoBar.info(
            title="CLI 登录",
            content="请在终端中扫描二维码完成登录",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=10000,
            parent=self,
        )

    def auto_connect_cli(self):
        """自动检查和连接 CLI"""
        self._check_cli()
