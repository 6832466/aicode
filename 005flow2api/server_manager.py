"""Manage Chrome CDP connectivity for local Gemini automation.

Replaces the old flow2api subprocess management. In local mode the app
connects directly to the user's Chrome via --remote-debugging-port instead
of running a separate API server.
"""
import shutil
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QProcess, Signal, QObject, QTimer


def find_chrome_path() -> str:
    """Find Chrome/Chromium executable path. Returns empty string if not found."""
    candidates = [
        Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files/Google/Chrome Beta/Application/chrome.exe"),
        Path("C:/Program Files/Google/Chrome Dev/Application/chrome.exe"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    found = shutil.which("chrome") or shutil.which("chromium") or shutil.which("google-chrome")
    return found or ""


def check_dependencies() -> tuple[bool, str]:
    """Check if playwright is installed. Returns (ok, message)."""
    try:
        __import__("playwright")
        return True, ""
    except ImportError:
        return False, (
            "playwright 未安装，请运行:\n"
            "pip install playwright\n"
            "python -m playwright install chromium"
        )


# ---------------------------------------------------------------------------
# Legacy helpers — kept for main_window.py compatibility (used by remote mode
# and settings dialog).
# ---------------------------------------------------------------------------

def read_flow2api_config() -> dict[str, str]:
    """Stub: return empty config since flow2api server is no longer used.

    In local CDP mode there is no API server or api_key.  The remote mode
    path in main_window.py reads this dict to decide whether to copy the
    key — returning empty values preserves the existing remote-mode logic
    without a server.
    """
    return {"api_key": "", "host": "localhost", "port": "0"}


# ---------------------------------------------------------------------------
# ServerManager — Chrome CDP connection lifecycle
# ---------------------------------------------------------------------------

class ServerManager(QObject):
    """Manages the Chrome CDP connection for local Gemini automation.

    Signal names and lifecycle are kept compatible with the old flow2api
    ServerManager so that main_window.py requires minimal changes.
    """

    state_changed = Signal(str)       # "stopped", "starting", "running", "error"
    log_line = Signal(str)            # diagnostic messages
    server_url_changed = Signal(str)  # CDP URL when connected (e.g. http://localhost:9222)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "stopped"
        self._check_timer: QTimer | None = None

    # -- public properties -------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == "running"

    # -- controls ----------------------------------------------------------

    def start_server(self):
        """Connect to local Chrome CDP."""
        import socket

        self._set_state("starting")
        self.log_line.emit("正在连接 Chrome 调试端口…")

        chrome_path = self._get_chrome_path()
        if not chrome_path:
            self._set_state("error")
            self.log_line.emit("❌ 未找到 Chrome 浏览器，请安装 Chrome 或设置 BROWSER_EXECUTABLE_PATH")
            return

        from gemini_cdp import GeminiCDPClient
        client = GeminiCDPClient()

        # Quick TCP check — is port already open?
        host = "127.0.0.1"
        port = 9222
        try:
            from config import cfg
            port = cfg.chrome_debug_port.value
        except Exception:
            pass

        port_open = False
        try:
            s = socket.socket()
            s.settimeout(2)
            s.connect((host, port))
            s.close()
            port_open = True
        except Exception:
            pass

        if port_open:
            # Chrome debug port is already listening — just connect.
            # Retry a few times in case auth prompt needs time.
            for attempt in range(6):
                ok, msg = client.check_connection()
                if ok:
                    self._set_state("running")
                    self.server_url_changed.emit(client._cdp_url)
                    self.log_line.emit(f"✅ {msg}")
                    return
                if attempt < 5:
                    self.log_line.emit(f"连接中 ({attempt + 1}/6) — {msg.split(chr(10))[0]}")
                    import time
                    time.sleep(1)
            # Port open but CDP failed — probably auth prompt
            self._set_state("error")
            self.log_line.emit(
                f"❌ Chrome 调试端口已开启但连接失败\n"
                f"   请确认 chrome://inspect/#remote-debugging 中已点击「允许」"
            )
            return

        # Port not open — show instructions instead of killing Chrome.
        # Force-killing Chrome corrupts the user profile and causes the crash
        # recovery dialog to block the debug port from opening.
        if self._is_chrome_running():
            self._set_state("error")
            self.log_line.emit(
                "❌ Chrome 正在运行但未开启调试端口\n"
                "   请在 Chrome 地址栏打开 chrome://inspect/#remote-debugging\n"
                "   点击「允许」后重试连接"
            )
        else:
            # Chrome not running — safe to launch
            self.log_line.emit("Chrome 未运行，正在启动（调试模式）…")
            ok2, msg2 = self._launch_chrome(chrome_path)
            if ok2:
                self._check_retries = 0
                self._check_max = 40
                self._check_timer = QTimer(self)
                self._check_timer.timeout.connect(lambda: self._poll_chrome_ready(client))
                self._check_timer.start(500)
            else:
                self._set_state("error")
                self.log_line.emit(f"❌ {msg2}")

    def stop_server(self):
        """Mark CDP connection as stopped (Chrome itself keeps running)."""
        if self._check_timer:
            self._check_timer.stop()
            self._check_timer = None
        self._set_state("stopped")
        self.log_line.emit("Chrome CDP 连接已断开")

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _is_chrome_running() -> bool:
        """Check if any Chrome browser process is currently running."""
        import subprocess
        try:
            result = subprocess.run(
                ["tasklist", "/fi", "imagename eq chrome.exe", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=5,
            )
            return "chrome.exe" in result.stdout.lower()
        except Exception:
            return False

    def _set_state(self, state: str):
        self._state = state
        self.state_changed.emit(state)

    def _poll_chrome_ready(self, client):
        self._check_retries += 1
        ok, msg = client.check_connection()
        if ok:
            if self._check_timer:
                self._check_timer.stop()
                self._check_timer = None
            self._set_state("running")
            self.server_url_changed.emit(client._cdp_url)
            self.log_line.emit(f"✅ Chrome 已连接 — {client._cdp_url}")
            return
        if self._check_retries >= self._check_max:
            if self._check_timer:
                self._check_timer.stop()
                self._check_timer = None
            self._set_state("error")
            self.log_line.emit(f"❌ Chrome 启动超时 — {msg}")
            return
        self.log_line.emit(f"等待 Chrome 就绪 ({self._check_retries}/{self._check_max})…")

    def _get_chrome_path(self) -> str:
        """Get Chrome executable path from config, falling back to auto-detect."""
        try:
            from config import cfg
            if cfg.chrome_exe_path.value:
                p = Path(cfg.chrome_exe_path.value)
                if p.exists():
                    return str(p)
        except Exception:
            pass
        return find_chrome_path()

    @staticmethod
    def _get_short_path(path: Path) -> str:
        """Get 8.3 short path to avoid space issues in Chrome arguments."""
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(512)
        GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        GetShortPathNameW.restype = wintypes.DWORD
        ret = GetShortPathNameW(str(path), buf, 512)
        if 0 < ret < 512:
            return buf.value
        return str(path)

    def _launch_chrome(self, chrome_path: str) -> tuple[bool, str]:
        """Launch Chrome with --remote-debugging-port. Returns (ok, message).

        Does NOT kill existing Chrome — caller must ensure Chrome is not running
        before calling this method.
        """
        import subprocess
        import tempfile
        import os

        port = 9222
        try:
            from config import cfg
            port = cfg.chrome_debug_port.value
        except Exception:
            pass

        # Use the user's real Chrome profile so login is preserved.
        # Must use short path (8.3) because Chrome's argument parser has
        # trouble with spaces in --user-data-dir on Windows.
        user_data = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
        user_data_short = self._get_short_path(user_data)

        # Write a temp .bat and execute it.  On Windows, subprocess.Popen
        # with list args uses CreateProcess (no ShellExecute), which causes
        # Chrome to not open the debug port.  cmd's start uses ShellExecute.
        bat_path = None
        try:
            fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="chrome_launch_")
            os.close(fd)
            with open(bat_path, "w", encoding="ascii") as f:
                f.write("@echo off\r\n")
                f.write(f'start "" "{chrome_path}"'
                        f' --remote-debugging-port={port}'
                        f' --user-data-dir="{user_data_short}"'
                        f' --no-first-run --no-default-browser-check'
                        f' --disable-session-crashed-bubble\r\n')
            subprocess.Popen(
                [bat_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True, f"Chrome 已启动 (调试端口: {port})"
        except FileNotFoundError:
            return False, f"找不到 Chrome 可执行文件: {chrome_path}"
        except Exception as e:
            return False, f"启动 Chrome 失败: {e}"
        finally:
            # Clean up the temp .bat after a short delay
            if bat_path:
                try:
                    import threading
                    threading.Timer(5.0, lambda: os.unlink(bat_path) if os.path.exists(bat_path) else None).start()
                except Exception:
                    pass
