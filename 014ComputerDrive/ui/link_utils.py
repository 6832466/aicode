"""在 Windows 上可靠打开链接、复制文本。"""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from services.url_normalize import normalize_nvidia_url


def is_web_url(text: str) -> bool:
    return (text or "").strip().lower().startswith(("http://", "https://"))


def _find_browsers() -> list[str]:
    """扫描已安装浏览器的可执行文件路径。"""
    found: list[str] = []
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LocalAppData", "")

    # Chrome
    candidates = [
        os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
    ]
    if local_appdata:
        candidates.append(
            os.path.join(local_appdata, "Google", "Chrome", "Application", "chrome.exe")
        )
    for p in candidates:
        if os.path.isfile(p):
            found.append(p)
            break

    # Edge
    for base in (program_files_x86, program_files):
        edge = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
        if os.path.isfile(edge):
            found.append(edge)
            break

    # Firefox
    for base in (program_files, program_files_x86):
        ff = os.path.join(base, "Mozilla Firefox", "firefox.exe")
        if os.path.isfile(ff):
            found.append(ff)
            break

    return found


def open_url(url: str) -> bool:
    """打开 http(s) 链接 — 优先直接调用浏览器 exe，绕过系统协议关联。"""
    url = normalize_nvidia_url((url or "").strip())
    if not is_web_url(url):
        return False

    # 方案 1：直接调用已安装的浏览器（最可靠，不依赖 Windows 协议关联）
    for browser in _find_browsers():
        try:
            subprocess.Popen([browser, url])  # noqa: S603
            return True
        except Exception:
            continue

    # 方案 2：Windows ShellExecute
    if sys.platform == "win32":
        try:
            os.startfile(url)  # noqa: S606
            return True
        except OSError:
            pass

    # 方案 3：webbrowser 标准库
    try:
        if webbrowser.open(url):
            return True
    except Exception:
        pass

    # 方案 4：Qt QDesktopServices
    return QDesktopServices.openUrl(QUrl(url))


def copy_text(text: str) -> None:
    QApplication.clipboard().setText(text or "")