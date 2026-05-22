"""主窗口 - 导航栏 + 页面切换 + 信号连线"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QWidget, QStackedWidget, QSystemTrayIcon, QMenu,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QAction, QCloseEvent
from qfluentwidgets import (
    NavigationInterface, NavigationItemPosition, FluentIcon,
    InfoBar, InfoBarPosition,
)

from gui.config import ConfigManager
from gui.history_db import HistoryDatabase
from gui.ui.home_page import HomePage
from gui.ui.downloading_page import DownloadingPage
from gui.ui.history_page import HistoryPage
from gui.ui.logs_page import LogsPage
from gui.ui.settings_page import SettingsPage
from gui.workers.download_worker import DownloadQueueManager
from gui.workers.log_handler import setup_logging

logger = logging.getLogger("hongguo")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self._db = HistoryDatabase()

        # 下载队列管理器 (全局, 各页面共享)
        self._queue_manager = DownloadQueueManager(
            max_concurrent=self.config.max_concurrent,
            max_retries=self.config.max_retries,
        )

        # 各页面 (延迟创建)
        self._pages: dict[str, QWidget] = {}

        # 日志处理器
        self._log_handler = setup_logging()

        self._setup_window()
        self._setup_navigation()
        self._setup_tray()
        self._connect_signals()
        self._connect_download_queue()
        self._connect_settings()

        self._switch_page("home")  # 默认打开首页

        logger.info("乐乐剧集下载器 启动完成")

    def _setup_window(self):
        self.setWindowTitle("乐乐剧集下载器")
        self.resize(1200, 800)
        self.setMinimumSize(960, 600)

        # 窗口图标
        icon_path = Path(__file__).parent.parent.parent / "1.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)

    def _setup_navigation(self):
        self._nav = NavigationInterface(self, showReturnButton=False)
        central = self.centralWidget()
        layout = central.layout()
        layout.insertWidget(0, self._nav)

        self._nav.addItem(
            routeKey="home", icon=FluentIcon.HOME, text="首页",
            onClick=lambda: self._switch_page("home"),
        )
        self._nav.addItem(
            routeKey="downloading", icon=FluentIcon.DOWNLOAD, text="下载",
            onClick=lambda: self._switch_page("downloading"),
        )
        self._nav.addItem(
            routeKey="history", icon=FluentIcon.HISTORY, text="历史",
            onClick=lambda: self._switch_page("history"),
        )
        self._nav.addItem(
            routeKey="logs", icon=FluentIcon.DOCUMENT, text="日志",
            onClick=lambda: self._switch_page("logs"),
        )
        self._nav.addItem(
            routeKey="settings", icon=FluentIcon.SETTING, text="设置",
            onClick=lambda: self._switch_page("settings"),
            position=NavigationItemPosition.BOTTOM,
        )
        self._nav.setCurrentItem("home")

    def _get_page(self, key: str):
        if key not in self._pages:
            if key == "home":
                page = HomePage(self.config)
                page.start_download.connect(self._on_start_download)
                self._pages[key] = page
            elif key == "downloading":
                page = DownloadingPage()
                page.set_queue_manager(self._queue_manager)
                self._pages[key] = page
            elif key == "history":
                page = HistoryPage(self.config)
                page.re_download.connect(self._on_re_download)
                self._pages[key] = page
            elif key == "logs":
                self._pages[key] = LogsPage()
            elif key == "settings":
                self._pages[key] = SettingsPage(self.config)
            self._stack.addWidget(self._pages[key])
        return self._pages[key]

    def _switch_page(self, key: str):
        page = self._get_page(key)
        self._stack.setCurrentWidget(page)
        self._nav.setCurrentItem(key)
        # 切换到历史页时自动刷新
        if key == "history":
            page.refresh()

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return
        self._tray = QSystemTrayIcon(QIcon(), self)
        self._tray.setToolTip("乐乐剧集下载器")
        menu = QMenu()
        show_action = QAction("显示主窗口")
        show_action.triggered.connect(self.show)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction("退出")
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: self.show() if reason == QSystemTrayIcon.DoubleClick else None
        )
        self._tray.show()

    def _connect_signals(self):
        # 日志 Handler → LogsPage
        logs_page = self._get_page("logs")
        self._log_handler.log_signal.connect(logs_page.append_log)

    def _connect_download_queue(self):
        """下载队列完成 → 历史记录"""
        self._queue_manager.all_done.connect(self._on_all_downloads_done)

    def _connect_settings(self):
        """设置变更 → 更新队列管理器"""
        page = self._get_page("settings")
        page.max_concurrent_changed.connect(self._queue_manager.set_max_concurrent)
        page.max_retries_changed.connect(self._queue_manager.set_max_retries)

    # ===== 下载流程 =====

    def _on_start_download(self, selected_episodes: list, output_dir: str,
                            vid_list: list, base_params: dict, page_path: str):
        """HomePage 点击开始下载 → 立即入队, 后台获取播放地址"""
        logger.info(f"[MAIN] _on_start_download received: episodes={selected_episodes}")
        home: HomePage = self._get_page("home")
        series_info = home._current_series_info
        series_name = series_info.get("series_name", "未知")
        series_id = series_info.get("series_id", "")
        cover_url = series_info.get("series_cover", "")
        total = len(home._current_vid_list)
        logger.info(f"[MAIN] series={series_name}, id={series_id}, total={total}, vids_received={len(vid_list)}, page_path={page_path}")

        from hgDown import sanitize_filename
        output_path = Path(output_dir) if output_dir else Path.home() / "Desktop"
        series_folder = output_path / sanitize_filename(series_name)
        logger.info(f"[MAIN] output_folder={series_folder}")

        # 必须在 add_series_group 之前确保下载页已创建并连接信号,
        # 否则 series_group_added 信号会因无接收者而丢失, 导致卡片不显示
        self._get_page("downloading")

        try:
            gid, tids = self._queue_manager.add_series_group(
                series_name=series_name,
                episodes=selected_episodes,
                vid_list=vid_list,
                base_params=base_params,
                page_path=page_path,
                output_dir=output_path,
                cover_url=cover_url,
                total_episodes=total,
            )
            logger.info(f"[MAIN] add_series_group OK: gid={gid}, tids={tids}")
        except Exception as e:
            logger.exception(f"[MAIN] add_series_group failed: {e}")
            InfoBar.error("下载失败", f"无法创建下载任务: {e}", parent=self)
            return

        # 保存历史记录
        try:
            self._db.insert(
                series_id=series_id,
                series_name=series_name,
                cover_url=cover_url,
                episodes=selected_episodes,
                total_episodes=total,
                quality="720P",
                status="downloading",
                local_path=str(series_folder),
            )
        except Exception as e:
            logger.warning(f"[MAIN] 历史记录保存失败 (不影响下载): {e}")

        self._switch_page("downloading")
        logger.info(f"[MAIN] 已加入队列: {series_name} — {len(tids)} 集 → {series_folder}")

    def _on_all_downloads_done(self, success: int, fail: int):
        logger.info(f"全部下载完成: 成功 {success}, 失败 {fail}")

    def _on_re_download(self, series_id: str, episodes: list):
        """历史页点击重新下载 → 跳转首页解析并自动开始下载"""
        if not series_id:
            InfoBar.error("记录不完整", "该历史记录缺少剧集 ID，请使用分享链接重新解析",
                          duration=5000, parent=self, position=InfoBarPosition.TOP_RIGHT)
            return
        self._switch_page("home")
        home: HomePage = self._get_page("home")
        home.set_re_download_episodes(episodes)
        home._input_edit.setText(series_id)
        home._on_parse()  # 触发解析 → 完成后自动选中并开始下载

    # ===== 窗口关闭 =====

    def closeEvent(self, event: QCloseEvent):
        if self.config.close_behavior == "tray" and self._tray:
            self.hide()
            InfoBar.info(
                "已最小化到系统托盘",
                "点击托盘图标可重新打开",
                duration=2000,
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
            )
            event.ignore()
        else:
            logger.info("应用程序退出")
            if self._tray:
                self._tray.hide()
            event.accept()
