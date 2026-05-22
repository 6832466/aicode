from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """应用根目录，frozen 时返回 exe 所在目录"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def app_icon_path() -> str:
    """返回图标文件路径，同时检查 _internal/ 回退路径"""
    root = app_root()
    candidates = [
        root / "1.ico",
        root / "_internal" / "1.ico",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(candidates[0])


APP_NAME = "比特浏览器管理工具"
SETTINGS_SCOPE = "BtChrome-Manager"
SETTINGS_KEY_API_URL = "api_url"
SETTINGS_KEY_BROWSER_PATH = "browser_path"
SETTINGS_KEY_REQUEST_TIMEOUT = "request_timeout"
DEFAULT_BROWSER_PATH = r"D:\Program Files\bitbrowser\比特浏览器.exe"

API_DEFAULT_URL = "http://127.0.0.1:54345"
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 1.0
RETRY_STATUSES = {429, 502, 503, 504}

PAGE_SIZE = 20
MONITOR_INTERVAL_MS = 5000
