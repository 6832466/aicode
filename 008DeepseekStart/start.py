"""
Codex Bridge Launcher — 管理 codex-bridge 代理的启动/停止/配置
"""
import sys
import json
import secrets
import shutil
import webbrowser
from html import escape as html_escape
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtGui import QFont, QIcon, QAction
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSystemTrayIcon, QMenu,
)

from qfluentwidgets import (
    FluentIcon, LineEdit, PushButton, PrimaryPushButton,
    TextEdit, InfoBar, CardWidget, BodyLabel, StrongBodyLabel,
    TitleLabel, setTheme, Theme, PasswordLineEdit, SpinBox,
    TransparentToolButton, setThemeColor, IndeterminateProgressBar,
    ToolButton, isDarkTheme,
)

# ── 路径 & 常量 ──────────────────────────────────────────────

def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


ROOT = app_root()
BRIDGE_DIR = ROOT / "codex-bridge"
CONFIG_FILE = ROOT / "config.json"
ENV_FILE = BRIDGE_DIR / ".env"
NODE_SCRIPT = BRIDGE_DIR / "proxy.mjs"


def _find_data(file_name: str) -> Path:
    """查找数据文件，兼容 PyInstaller COLLECT 模式（文件在 _internal/ 子目录）。"""
    path = ROOT / file_name
    if path.exists():
        return path
    internal = ROOT / "_internal" / file_name
    if internal.exists():
        return internal
    return path


ICON_FILE = _find_data("1.ico")
NODE_PATH: str | None = shutil.which("node")

GITHUB_URL = "https://github.com/wujfeng712-ui/codex-bridge"

DEFAULT_CONFIG = {
    "deepseek_api_key": "",
    "proxy_auth_key": "",
    "port": 4000,
}

WIN_TITLE = "Codex Bridge启动器    微信：rpalele"
WIN_WIDTH = 720
WIN_HEIGHT = 640
MAX_CONSOLE_BLOCKS = 100
AUTO_SAVE_DEBOUNCE_MS = 500

# 日志颜色常量
C_SUCCESS = "#4ade80"
C_WARN = "#fbbf24"
C_ERROR = "#f87171"
C_INFO = "#60a5fa"


# ── 工具函数 ──────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(data)
            return cfg
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_auth_key() -> str:
    return f"sk-proxy-local-{secrets.token_hex(24)}"


def check_node_available() -> bool:
    return NODE_PATH is not None


def write_env_file(api_key: str, auth_key: str, port: int):
    ENV_FILE.write_text(
        f"PROXY_AUTH_KEY={auth_key}\n"
        f"DEEPSEEK_API_KEY={api_key}\n"
        f"PROXY_PORT={port}\n",
        encoding="utf-8",
    )


def console_style() -> str:
    if isDarkTheme():
        return """
            QTextEdit {
                background-color: #1a1a2e;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #45475a;
            }
        """
    else:
        return """
            QTextEdit {
                background-color: #f4f4f5;
                color: #1c1c1c;
                border: 1px solid #d4d4d8;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #a1a1aa;
            }
        """


def status_style(running: bool) -> str:
    if running:
        return "font-size: 13px; font-weight: bold; color: #10b981;"
    if isDarkTheme():
        return "font-size: 13px; color: #737373;"
    return "font-size: 13px; color: #a1a1aa;"


def subtitle_color() -> str:
    return "#a0a0a0" if isDarkTheme() else "#71717a"


def log_default_color() -> str:
    return "#cdd6f4" if isDarkTheme() else "#3f3f46"


def log_ts_color() -> str:
    return "#6c7086" if isDarkTheme() else "#a1a1aa"


# ── 主窗口 ──────────────────────────────────────────────

class LauncherWindow(QWidget):

    def __init__(self):
        super().__init__()
        self._process: QProcess | None = None
        self._config = load_config()
        if not self._config["proxy_auth_key"]:
            self._config["proxy_auth_key"] = generate_auth_key()
            save_config(self._config)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)

        self._setup_tray()
        self._setup_ui()
        self._setup_signals()
        self._check_prerequisites()

    @property
    def _running(self) -> bool:
        return (
            self._process is not None
            and self._process.state() != QProcess.ProcessState.NotRunning
        )

    def _setup_ui(self):
        self.setWindowTitle(WIN_TITLE)
        self.resize(WIN_WIDTH, WIN_HEIGHT)
        self.setMinimumSize(520, 440)

        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))

        self.setObjectName("launcherWindow")
        self.setStyleSheet("#launcherWindow { background-color: #202020; }")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 20, 28, 24)
        main_layout.setSpacing(14)

        # 头部
        header_layout = QHBoxLayout()
        title = TitleLabel(WIN_TITLE)
        self.github_btn = ToolButton(FluentIcon.GLOBE)
        self.github_btn.setToolTip("在 GitHub 上查看 codex-bridge 源码")
        self.github_btn.setFixedSize(32, 32)
        self.github_btn.setStyleSheet("QToolButton { border-radius: 6px; }")
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.github_btn)
        main_layout.addLayout(header_layout)

        subtitle = BodyLabel("零依赖本地代理 — 让 Codex CLI 通过 DeepSeek 运行")
        subtitle.setStyleSheet(f"color: {subtitle_color()};")
        main_layout.addWidget(subtitle)

        # 设置卡片
        settings_card = CardWidget()
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(20, 16, 20, 16)
        settings_layout.setSpacing(14)

        settings_header = StrongBodyLabel("代理设置")
        settings_layout.addWidget(settings_header)

        # DeepSeek API Key
        api_layout = QHBoxLayout()
        api_label = BodyLabel("DeepSeek API Key")
        api_label.setFixedWidth(140)
        self.api_key_input = PasswordLineEdit()
        self.api_key_input.setPlaceholderText("sk-... 从 platform.deepseek.com 获取")
        self.api_key_input.setText(self._config["deepseek_api_key"])
        api_layout.addWidget(api_label)
        api_layout.addWidget(self.api_key_input)
        settings_layout.addLayout(api_layout)

        # Proxy Auth Key
        auth_layout = QHBoxLayout()
        auth_label = BodyLabel("Proxy Auth Key")
        auth_label.setFixedWidth(140)
        self.auth_key_input = LineEdit()
        self.auth_key_input.setText(self._config["proxy_auth_key"])
        self.auth_key_input.setReadOnly(True)
        self.copy_auth_btn = PushButton(FluentIcon.COPY, " 复制")
        self.copy_auth_btn.setToolTip("复制密钥到剪贴板")
        self.regenerate_btn = PushButton(FluentIcon.SYNC, " 重新生成")
        self.regenerate_btn.setToolTip("重新生成密钥")
        auth_layout.addWidget(auth_label)
        auth_layout.addWidget(self.auth_key_input)
        auth_layout.addWidget(self.copy_auth_btn)
        auth_layout.addWidget(self.regenerate_btn)
        settings_layout.addLayout(auth_layout)

        # 端口
        port_layout = QHBoxLayout()
        port_label = BodyLabel("监听端口")
        port_label.setFixedWidth(140)
        self.port_input = SpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(self._config["port"])
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_input)
        port_layout.addStretch()
        settings_layout.addLayout(port_layout)

        # 代理地址
        url_layout = QHBoxLayout()
        url_label = BodyLabel("代理地址")
        url_label.setFixedWidth(140)
        self.proxy_url_input = LineEdit()
        self.proxy_url_input.setReadOnly(True)
        self._update_proxy_url()
        self.copy_url_btn = PushButton(FluentIcon.COPY, " 复制")
        self.copy_url_btn.setToolTip("复制代理地址到剪贴板")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.proxy_url_input)
        url_layout.addWidget(self.copy_url_btn)
        settings_layout.addLayout(url_layout)

        main_layout.addWidget(settings_card)

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.start_btn = PrimaryPushButton(FluentIcon.PLAY, " 启动代理")
        self.start_btn.setMinimumWidth(150)
        self.start_btn.setMinimumHeight(38)

        self.stop_btn = PushButton(FluentIcon.PAUSE, " 停止代理")
        self.stop_btn.setMinimumWidth(150)
        self.stop_btn.setMinimumHeight(38)
        self.stop_btn.setEnabled(False)

        self.status_indicator = QLabel("● 已停止")
        self.status_indicator.setStyleSheet(status_style(False))
        self.status_indicator.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addSpacing(16)
        btn_layout.addWidget(self.status_indicator)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self.progress_bar = IndeterminateProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 控制台输出
        console_card = CardWidget()
        console_layout = QVBoxLayout(console_card)
        console_layout.setContentsMargins(12, 12, 12, 12)
        console_layout.setSpacing(8)

        console_header_layout = QHBoxLayout()
        console_label = StrongBodyLabel("控制台输出")
        self.clear_console_btn = TransparentToolButton(FluentIcon.DELETE)
        self.clear_console_btn.setToolTip("清空输出")
        console_header_layout.addWidget(console_label)
        console_header_layout.addStretch()
        console_header_layout.addWidget(self.clear_console_btn)
        console_layout.addLayout(console_header_layout)

        self.console_output = TextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setFont(QFont("Consolas, Cascadia Code, Courier New", 10))
        self.console_output.setStyleSheet(console_style())
        self.console_output.setMinimumHeight(200)
        console_layout.addWidget(self.console_output)

        main_layout.addWidget(console_card, stretch=1)

    def _setup_tray(self):
        icon = QIcon(str(ICON_FILE)) if ICON_FILE.exists() else QIcon()
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(WIN_TITLE)

        menu = QMenu()
        show_action = QAction("显示窗口", menu)
        show_action.triggered.connect(self._show_from_tray)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def _quit_from_tray(self):
        if self._running:
            self._do_stop()
        self._tray.hide()
        QApplication.quit()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _setup_signals(self):
        self.start_btn.clicked.connect(self.start_proxy)
        self.stop_btn.clicked.connect(self.stop_proxy)
        self.clear_console_btn.clicked.connect(self.console_output.clear)
        self.github_btn.clicked.connect(lambda: webbrowser.open(GITHUB_URL))
        self.api_key_input.textChanged.connect(self._schedule_save)
        self.port_input.valueChanged.connect(self._schedule_save)
        self.port_input.valueChanged.connect(self._update_proxy_url)
        self.regenerate_btn.clicked.connect(self._regenerate_auth)
        self.copy_auth_btn.clicked.connect(lambda: self._copy_to_clipboard(
            self._config["proxy_auth_key"], "Proxy Auth Key"))
        self.copy_url_btn.clicked.connect(lambda: self._copy_to_clipboard(
            self.proxy_url_input.text(), f"代理地址 {self.proxy_url_input.text()}"))

    # ── 前置检查 ──

    def _check_prerequisites(self):
        ok = True
        if not check_node_available():
            self._append_log("[错误] 未检测到 Node.js", C_ERROR)
            self.start_btn.setEnabled(False)
            ok = False
        if not NODE_SCRIPT.exists():
            self._append_log("[错误] 未找到 codex-bridge/proxy.mjs", C_ERROR)
            self.start_btn.setEnabled(False)
            ok = False
        if ok:
            self._append_log("[系统] 环境就绪", C_SUCCESS)

    # ── 启动 ──

    def start_proxy(self):
        if self._running:
            return

        api_key = self.api_key_input.text().strip()
        if not api_key:
            InfoBar.error("缺少 API Key", "请先填写 DeepSeek API Key",
                          duration=5000, parent=self)
            return

        if NODE_PATH is None:
            InfoBar.error("Node.js 未找到", "请安装 Node.js 18+",
                          duration=5000, parent=self)
            return

        auth_key = self._config["proxy_auth_key"]
        port = self.port_input.value()
        write_env_file(api_key, auth_key, port)

        self._append_log("-" * 50, log_ts_color())
        self._append_log(f"[启动] 正在启动代理... 端口: {port}", C_INFO)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.setWorkingDirectory(str(BRIDGE_DIR))
        self._process.setProgram(NODE_PATH)
        self._process.setArguments(["--env-file=.env", "proxy.mjs"])
        self._process.readyRead.connect(self._read_output)
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)

        self._process.start()
        self._update_state(True)
        self._append_log("[启动] 进程已创建，等待就绪...", C_INFO)
        self.progress_bar.setVisible(True)

    # ── 停止 ──

    def stop_proxy(self):
        if not self._running:
            return
        self._append_log("[停止] 正在停止代理...", C_WARN)
        self._do_stop()

    def _do_stop(self):
        if self._process is None:
            return

        pid = self._process.processId()

        if self._process.state() == QProcess.ProcessState.NotRunning:
            self._finalize_stop()
            return

        # 断开 finished 信号，避免触发"意外退出"提示
        try:
            self._process.finished.disconnect(self._on_process_finished)
        except Exception:
            pass

        self._process.terminate()
        self._append_log("[停止] 已发送 terminate 信号", C_WARN)

        if not self._process.waitForFinished(1000):
            self._process.kill()
            self._append_log("[停止] terminate 未响应，已发送 kill", C_ERROR)
            if sys.platform == "win32" and pid:
                self._cleanup_win_process_tree(pid)
            self._process.waitForFinished(2000)

        self._finalize_stop()

    def _cleanup_win_process_tree(self, pid: int):
        if not pid:
            return
        import subprocess
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
            self._append_log(f"[停止] taskkill /T /PID {pid} 已执行", C_WARN)
        except Exception as e:
            self._append_log(f"[停止] taskkill 异常: {e}", C_ERROR)

    def _finalize_stop(self):
        if self._process is not None:
            try:
                self._process.close()
            except Exception:
                pass
            try:
                self._process.deleteLater()
            except Exception:
                pass
            self._process = None

        self.progress_bar.setVisible(False)
        self._update_state(False)
        self._append_log("[停止] 代理已停止，进程已清理", C_SUCCESS)

    # ── 进程回调 ──

    def _read_output(self):
        if not self._process:
            return
        try:
            data = self._process.readAll().data().decode("utf-8", errors="replace")
        except Exception:
            return
        if data:
            self._append_process_output(data)

    def _on_process_finished(self, exit_code, exit_status):
        self.progress_bar.setVisible(False)
        if exit_status == QProcess.ExitStatus.NormalExit:
            self._append_log(f"[系统] 代理已退出 (code={exit_code})", log_ts_color())
        else:
            self._append_log(f"[系统] 代理异常退出 (code={exit_code})", C_ERROR)

        self._update_state(False)
        if self._process is not None:
            self._process.deleteLater()
            self._process = None

        InfoBar.info("代理已停止", f"退出码: {exit_code}", duration=4000, parent=self)

    def _on_process_error(self, error):
        self.progress_bar.setVisible(False)
        self._update_state(False)

        err_msg = {
            QProcess.ProcessError.FailedToStart: "无法启动 — 检查 Node.js 安装",
            QProcess.ProcessError.Crashed: "进程崩溃",
            QProcess.ProcessError.Timedout: "操作超时",
            QProcess.ProcessError.WriteError: "写入错误",
            QProcess.ProcessError.ReadError: "读取错误",
            QProcess.ProcessError.UnknownError: "未知错误",
        }.get(error, f"错误码: {error}")

        self._append_log(f"[错误] {err_msg}", C_ERROR)
        InfoBar.error("代理启动失败", err_msg, duration=5000, parent=self)
        if self._process is not None:
            self._process.deleteLater()
            self._process = None

    # ── 状态更新 ──

    def _update_state(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.api_key_input.setEnabled(not running)
        self.port_input.setEnabled(not running)
        if running:
            self.status_indicator.setText("● 运行中")
        else:
            self.status_indicator.setText("● 已停止")
        self.status_indicator.setStyleSheet(status_style(running))

    # ── 控制台输出 ──

    def _append_process_output(self, text: str):
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        c = log_default_color()
        tsc = log_ts_color()
        ts = datetime.now().strftime("%H:%M:%S")

        parts = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                parts.append(
                    f'<span style="color:{tsc};">{ts}</span> '
                    f'<span style="color:{c};">[代理] {html_escape(stripped)}</span><br>'
                )

        if parts:
            self._insert_html("".join(parts))

    def _append_log(self, msg: str, color: str):
        ts = datetime.now().strftime("%H:%M:%S")
        html = (
            f'<span style="color:{log_ts_color()};">{ts}</span> '
            f'<span style="color:{color};">{html_escape(msg)}</span><br>'
        )
        self._insert_html(html)

    def _insert_html(self, html: str):
        cursor = self.console_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        cursor.insertHtml(html)
        self._trim_console()

    def _trim_console(self):
        if self.console_output.document().blockCount() > MAX_CONSOLE_BLOCKS:
            self.console_output.clear()

    # ── 配置持久化 ──

    def _schedule_save(self):
        self._save_timer.start(AUTO_SAVE_DEBOUNCE_MS)

    def _do_save(self):
        self._config["deepseek_api_key"] = self.api_key_input.text().strip()
        self._config["port"] = self.port_input.value()
        save_config(self._config)

    def _update_proxy_url(self):
        self.proxy_url_input.setText(f"http://127.0.0.1:{self.port_input.value()}/v1")

    def _copy_to_clipboard(self, value: str, label: str):
        QApplication.clipboard().setText(value)
        self._append_log(f"[配置] {label} 已复制到剪贴板", C_SUCCESS)
        InfoBar.success("已复制", f"{label} 已复制到剪贴板", duration=2000, parent=self)

    def _regenerate_auth(self):
        new_key = generate_auth_key()
        self._config["proxy_auth_key"] = new_key
        self.auth_key_input.setText(new_key)
        save_config(self._config)
        self._append_log("[配置] Proxy Auth Key 已重新生成", C_SUCCESS)
        InfoBar.success("密钥已更新", "Proxy Auth Key 已重新生成并保存",
                        duration=3000, parent=self)

    # ── 窗口关闭 ──

    def closeEvent(self, event):
        if self._running:
            self.hide()
            self._tray.showMessage(
                WIN_TITLE, "代理仍在运行，已最小化到托盘",
                QSystemTrayIcon.MessageIcon.Information, 2000,
            )
            event.ignore()
            return
        self._tray.hide()
        event.accept()


# ── 入口 ──────────────────────────────────────────────

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("CodexBridge")
    app.setOrganizationName("rpalele")

    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))

    setTheme(Theme.DARK)
    setThemeColor("#60a5fa")

    window = LauncherWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
