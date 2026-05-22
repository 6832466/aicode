import sys
import threading
import logging
import subprocess
import time
import urllib.request
from datetime import datetime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame
from PySide6.QtCore import Qt, QThread, Signal, QObject, QMetaObject, Q_ARG
from PySide6.QtGui import QCloseEvent, QIcon
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    SubtitleLabel, BodyLabel, InfoBar, InfoBarPosition,
    setTheme, Theme, isDarkTheme, MessageBox
)

from models import AppConfig, SendStatus, ChatMode, ReplyMessage
from send_panel import SendPanel
from reply_panel import ReplyPanel
from config_bar import ConfigBar, StatusBar
from automation import DoubaoAutomation
from log_panel import LogPanel, install_log_handler
from help_panel import HelpPanel
from template_panel import TemplatePanel

logger = logging.getLogger(__name__)


class AutomationWorker(QObject):
    status_changed = Signal(int, object)   # msg_id, SendStatus
    reply_received = Signal(object)        # ReplyMessage
    mode_changed = Signal(object)          # ChatMode
    log_message = Signal(str)
    finished = Signal()

    def __init__(self, engine: DoubaoAutomation, messages, start_index: int = 0):
        super().__init__()
        self.engine = engine
        self.messages = messages
        self.start_index = start_index

    def run(self):
        self.engine.on_status_change = lambda mid, s: self.status_changed.emit(mid, s)
        self.engine.on_reply_received = lambda r: self.reply_received.emit(r)
        self.engine.on_mode_changed = lambda m: self.mode_changed.emit(m)
        self.engine.on_log = lambda t: self.log_message.emit(t)
        self.engine.run(self.messages, self.start_index)
        self.finished.emit()


class MainWindow(FluentWindow):
    _connect_result = Signal(bool, str)  # success, message

    def __init__(self):
        super().__init__()
        self.config = AppConfig()
        self.engine = DoubaoAutomation(self.config)
        self._worker: AutomationWorker = None
        self._thread: QThread = None
        self._start_time: datetime = None
        self._success_count = 0
        self._fail_count = 0
        self._current_round = 0

        self._setup_window()
        self._setup_logging()
        self._connect_result.connect(self._on_connect_result)

    def _setup_window(self):
        self.setWindowTitle("乐乐豆包多轮对话自动化工具    微信：rpalele")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        import os
        icon_path = os.path.join(os.path.dirname(__file__), "1.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # ── 主界面 ──────────────────────────────────────────────────────
        central = QWidget()
        central.setObjectName("mainInterface")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 8, 16, 8)
        root_layout.setSpacing(8)

        self.config_bar = ConfigBar(self.config)
        self.config_bar.connect_browser_requested.connect(self._on_connect_browser)
        self.config_bar.start_requested.connect(self._on_start)
        self.config_bar.pause_requested.connect(self._on_pause)
        self.config_bar.resume_requested.connect(self._on_resume)
        self.config_bar.stop_requested.connect(self._on_stop)
        self.config_bar.new_chat_requested.connect(self._on_new_chat)

        config_frame = QFrame()
        config_frame.setFrameShape(QFrame.Shape.StyledPanel)
        config_frame_layout = QVBoxLayout(config_frame)
        config_frame_layout.setContentsMargins(0, 0, 0, 0)
        config_frame_layout.addWidget(self.config_bar)
        root_layout.addWidget(config_frame)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.send_panel = SendPanel()
        self.reply_panel = ReplyPanel()
        self.reply_panel.set_send_source(self.send_panel.get_messages)
        self.send_panel.start_from_index.connect(self._on_resume_from_index)
        self.reply_panel.reply_selected.connect(self.send_panel.table.selectRow)
        splitter.addWidget(self.send_panel)
        splitter.addWidget(self.reply_panel)
        splitter.setSizes([600, 600])
        root_layout.addWidget(splitter, 1)

        self.status_bar = StatusBar()
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_frame_layout = QVBoxLayout(status_frame)
        status_frame_layout.setContentsMargins(0, 0, 0, 0)
        status_frame_layout.addWidget(self.status_bar)
        root_layout.addWidget(status_frame)

        self.addSubInterface(central, FluentIcon.HOME, "主界面")

        # ── 日志页面 ─────────────────────────────────────────────────────
        self.log_panel = LogPanel()
        self.log_panel.setObjectName("logInterface")
        self.addSubInterface(self.log_panel, FluentIcon.DOCUMENT, "运行日志")

        # ── 模板管理页面 ──────────────────────────────────────────────────
        self.template_panel = TemplatePanel()
        self.template_panel.setObjectName("templateInterface")
        self.addSubInterface(self.template_panel, FluentIcon.EDIT, "模板管理")

        # ── 帮助页面 ─────────────────────────────────────────────────────
        self.help_panel = HelpPanel()
        self.help_panel.setObjectName("helpInterface")
        self.addSubInterface(
            self.help_panel, FluentIcon.HELP, "使用帮助",
            position=NavigationItemPosition.BOTTOM
        )

    def _setup_logging(self):
        install_log_handler()

    # ------------------------------------------------------------------ #
    #  Automation control                                                  #
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    #  Browser connection                                                  #
    # ------------------------------------------------------------------ #

    def _on_connect_browser(self):
        """Kill any Chrome without debug port, relaunch with CDP, then connect."""
        self.config_bar.connect_btn.setEnabled(False)
        self.config_bar.connect_btn.setText("连接中...")

        def _work():
            log = logging.getLogger(__name__)
            cdp_url = "http://localhost:9222/json/version"

            # 1. Check if CDP is already available
            try:
                urllib.request.urlopen(cdp_url, timeout=2)
                log.info("检测到 CDP 端口已就绪，直接连接")
                self._do_connect(log)
                return
            except Exception:
                pass

            # 2. Find Chrome executable
            import os, glob
            candidates = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
            ]
            # also check PATH and registry
            import shutil, winreg
            path_chrome = shutil.which("chrome") or shutil.which("google-chrome")
            if path_chrome:
                candidates.insert(0, path_chrome)
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                     r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
                reg_path, _ = winreg.QueryValueEx(key, "")
                if reg_path:
                    candidates.insert(0, reg_path)
            except Exception:
                pass

            chrome_exe = next((p for p in candidates if os.path.exists(p)), None)
            if not chrome_exe:
                log.error("找不到 Chrome 可执行文件，请手动用调试模式启动 Chrome")
                self._connect_done(False, "找不到 Chrome，请手动启动")
                return

            # 3. Kill existing Chrome processes
            log.info("正在关闭现有 Chrome 进程...")
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "chrome.exe"],
                    capture_output=True, timeout=10
                )
                time.sleep(1.5)
            except Exception as e:
                log.warning(f"关闭 Chrome 时出错（忽略）: {e}")

            # 4. Launch Chrome with debug port
            user_data = r"C:\Temp\chrome-doubao-debug"
            os.makedirs(user_data, exist_ok=True)
            log.info(f"正在启动调试版 Chrome: {chrome_exe}")
            try:
                subprocess.Popen([
                    chrome_exe,
                    "--remote-debugging-port=9222",
                    f"--user-data-dir={user_data}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "https://www.doubao.com/chat/",
                ])
            except Exception as e:
                log.error(f"启动 Chrome 失败: {e}")
                self._connect_done(False, f"启动 Chrome 失败: {e}")
                return

            # 5. Wait for CDP to become available (up to 15s)
            log.info("等待 Chrome 就绪...")
            for _ in range(30):
                time.sleep(0.5)
                try:
                    urllib.request.urlopen(cdp_url, timeout=1)
                    log.info("Chrome 已就绪")
                    break
                except Exception:
                    pass
            else:
                log.error("等待 Chrome 超时，请手动检查")
                self._connect_done(False, "Chrome 启动超时")
                return

            self._do_connect(log)

        threading.Thread(target=_work, daemon=True).start()

    def _do_connect(self, log):
        self.engine._pw = None
        self.engine._browser = None
        self.engine._page = None
        if self.engine.start_browser():
            log.info("浏览器连接成功")
            self._connect_result.emit(True, "")
        else:
            self._connect_result.emit(False, "连接失败，请查看日志")

    def _connect_done(self, success: bool, msg: str):
        self._connect_result.emit(success, msg)

    def _on_connect_result(self, success: bool, msg: str):
        self.config_bar.connect_btn.setEnabled(True)
        self.config_bar.connect_btn.setText("连接浏览器")
        if success:
            InfoBar.success("已连接", "Chrome 浏览器连接成功，可以开始使用",
                            parent=self, position=InfoBarPosition.TOP, duration=4000)
        else:
            InfoBar.error("连接失败", msg or "请查看运行日志",
                          parent=self, position=InfoBarPosition.TOP)

    def _ensure_browser(self) -> bool:
        """Connect to Chrome if not already connected."""
        if self.engine._browser:
            return True
        if not self.engine.start_browser():
            InfoBar.error("错误", "连接 Chrome 失败，请确保 Chrome 已用 --remote-debugging-port=9222 启动",
                          parent=self, position=InfoBarPosition.TOP)
            return False
        return True

    def _on_new_chat(self):
        if not self._ensure_browser():
            return
        self.engine.new_conversation(self.config.system_prompt)

    def _on_start(self):
        messages = self.send_panel.get_messages()
        if not messages:
            InfoBar.warning("提示", "请先添加要发送的消息", parent=self, position=InfoBarPosition.TOP)
            self.config_bar.set_finished()
            return
        if not self._ensure_browser():
            self.config_bar.set_finished()
            return
        self._start_execution(messages, 0)

    def _on_resume_from_index(self, index: int):
        messages = self.send_panel.get_messages()
        if not messages or index >= len(messages):
            return
        if not self._ensure_browser():
            return
        self._start_execution(messages, index)

    def _start_execution(self, messages, start_index: int):
        self._success_count = 0
        self._fail_count = 0
        self._current_round = 0
        self._start_time = datetime.now()

        self.status_bar.update(
            state="执行中",
            current_round=0,
            total=len(messages),
            mode="—",
            success=0,
            fail=0,
            pending=len(messages) - start_index,
            start_time=self._start_time.strftime("%H:%M:%S"),
        )

        self._thread = QThread()
        self._worker = AutomationWorker(self.engine, messages, start_index)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status_changed.connect(self._on_status_changed)
        self._worker.reply_received.connect(self._on_reply_received)
        self._worker.mode_changed.connect(self._on_mode_changed)
        self._worker.log_message.connect(lambda t: logging.getLogger("automation").info(t))
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_pause(self):
        self.engine.pause()
        self.status_bar.update(state="已暂停")

    def _on_resume(self):
        self.engine.resume()
        self.status_bar.update(state="执行中")

    def _on_stop(self):
        self.engine.stop()
        self.status_bar.update(state="已停止")

    def _on_status_changed(self, msg_id: int, status: SendStatus):
        self.send_panel.update_status(msg_id, status)
        if status == SendStatus.SENT:
            self._success_count += 1
            self._current_round += 1
        elif status == SendStatus.FAILED:
            self._fail_count += 1
        total = len(self.send_panel.get_messages())
        pending = len(self.send_panel.get_pending_messages())
        self.status_bar.update(
            current_round=self._current_round,
            total=total,
            success=self._success_count,
            fail=self._fail_count,
            pending=pending,
        )

    def _on_reply_received(self, reply: ReplyMessage):
        self.reply_panel.add_reply(reply)
        self.send_panel.update_reply_link(reply.send_id, reply.id)

    def _on_mode_changed(self, mode: ChatMode):
        self.status_bar.update(mode=mode.value)

    def _on_finished(self):
        self.config_bar.set_finished()
        self.status_bar.update(state="已完成")
        InfoBar.success("完成", f"全部消息处理完毕，成功 {self._success_count} 条，失败 {self._fail_count} 条",
                        parent=self, position=InfoBarPosition.TOP, duration=5000)

    def closeEvent(self, event: QCloseEvent):
        if self.engine._running:
            box = MessageBox("确认退出", "自动化任务正在运行，确定要退出吗？", self)
            if not box.exec():
                event.ignore()
                return
        self.engine.stop()
        self.engine.close_browser()
        super().closeEvent(event)
