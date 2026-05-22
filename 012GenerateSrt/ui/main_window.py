"""
主窗口 — FluentWindow 导航框架 + 模块集成
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QTimer
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
    InfoBar, InfoBarPosition,
)

from app.config import (
    WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT, app_icon_path,
    STATE_DONE, STATE_FAILED, STATE_STOPPED,
)
from app.models import TaskItem, BatchLogEntry
from app.queue_manager import QueueManager
from app.log_manager import LogManager
from app.license import License
from ui.pages.home_page import HomePage
from ui.pages.settings_page import SettingsPage
from ui.pages.history_page import HistoryPage

_debug_log = Path(__file__).parent.parent / "debug.log"
def _dbg(msg: str):
    ts = time.strftime("%H:%M:%S")
    with open(_debug_log, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] MW: {msg}\n")

logger = logging.getLogger(__name__)

# 抑制第三方库 DEBUG 日志
for lib in ("asyncio", "aiohttp", "urllib3"):
    logging.getLogger(lib).setLevel(logging.WARNING)


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self._init_window()
        self._init_modules()
        self._init_pages()
        self._init_navigation()
        self._connect_signals()
        self._setup_logging()

    # ═══════════════════════════════════════════
    #  初始化
    # ═══════════════════════════════════════════

    def _init_window(self):
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _init_modules(self):
        """初始化后端模块"""
        self.license = License()
        self.queue_manager = QueueManager()
        self.log_manager = LogManager()

    def _init_pages(self):
        self.home_page = HomePage(self)
        self.settings_page = SettingsPage(self)
        self.history_page = HistoryPage(self)

    def _init_navigation(self):
        self.addSubInterface(
            self.home_page, FluentIcon.HOME, "主页",
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.settings_page, FluentIcon.SETTING, "设置",
            NavigationItemPosition.BOTTOM,
        )
        self.addSubInterface(
            self.history_page, FluentIcon.HISTORY, "历史记录",
            NavigationItemPosition.BOTTOM,
        )

    def _setup_logging(self):
        """日志配置（抑制 DEBUG 噪音）"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )

    def _connect_signals(self):
        """连接所有信号"""
        # 主页 → 队列管理器
        self.home_page.task_added.connect(self._on_task_added)
        self.home_page.task_removed.connect(self.queue_manager.remove_task)
        self.home_page.start_all.connect(self._on_start_all)
        self.home_page.pause_all.connect(self.queue_manager.pause)
        self.home_page.stop_all.connect(self._on_stop_all)
        self.home_page.reprocess_task.connect(self._on_reprocess)
        self.home_page.open_srt.connect(self._on_open_srt)

        # 队列管理器 → 主页
        self.queue_manager.task_updated.connect(self.home_page.update_task)
        self.queue_manager.all_completed.connect(self._on_all_completed)
        self.queue_manager.log_message.connect(self.home_page.log)

    # ═══════════════════════════════════════════
    #  信号处理
    # ═══════════════════════════════════════════

    def _on_task_added(self, task: TaskItem):
        """任务添加到列表后同步到队列管理器"""
        _dbg(f"_on_task_added: {task.file_name}, state={task.state}")
        self.queue_manager.add_task(task)
        self.home_page.log(f"已添加: {task.file_name}")

    def _on_start_all(self):
        """开始处理全部"""
        _dbg("_on_start_all: called")
        self._sync_scripts()
        tasks = self.home_page.get_tasks()
        _dbg(f"_on_start_all: tasks={len(tasks)}")
        for t in tasks:
            if t.id not in [x.id for x in self.queue_manager.get_all_tasks()]:
                self.queue_manager.add_task(t)
        _dbg("_on_start_all: calling queue_manager.start()")
        self.queue_manager.start()

    def _on_stop_all(self):
        """停止全部"""
        self.queue_manager.stop()
        self.home_page.set_processing_state(False)

    def _on_reprocess(self, task_id: str):
        """重新处理单个任务"""
        tasks = self.home_page.get_tasks()
        for t in tasks:
            if t.id == task_id:
                t.state = "pending"
                t.progress = 0.0
                t.error = None
                t.srt_path = None
                self.queue_manager.add_task(t)
                self.home_page.update_task(t)
                self.queue_manager.start()
                return

    def _on_open_srt(self, task_id: str):
        """打开字幕文件"""
        import os
        tasks = self.home_page.get_tasks()
        for t in tasks:
            if t.id == task_id and t.srt_path and os.path.exists(t.srt_path):
                os.startfile(t.srt_path)
                return

    def _on_all_completed(self):
        """全部完成"""
        self.home_page.set_processing_state(False)
        self._write_history()
        self.show_success("处理完成", "所有任务已完成，请查看历史记录。")

    def _sync_scripts(self):
        """同步主页动态编辑的文稿到任务数据"""
        # 文稿已经在 home_page._on_script_changed 中实时更新
        pass

    def _write_history(self):
        """写入历史记录"""
        tasks = self.home_page.get_tasks()
        for t in tasks:
            if t.state in (STATE_DONE, STATE_FAILED, STATE_STOPPED):
                entry = BatchLogEntry(
                    task_id=t.id,
                    file_name=t.file_name,
                    mode=t.mode,
                    state=t.state,
                    srt_path=t.srt_path,
                    error=t.error,
                    processed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                self.log_manager.add_entry(entry)
        self.home_page.log("历史记录已保存")

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