"""设置管理器 - JSON持久化"""
import json
import os
from PySide6.QtCore import QObject, Signal


DEFAULT_SETTINGS = {
    "download": {
        "save_path": os.path.expanduser("~/Videos"),
        "max_concurrent": 3,
        "speed_limit": 0,  # 0=不限, 单位 KB/s
        "auto_retry": True,
        "retry_count": 3,
        "notify_complete": True,
        "open_folder_after_done": False,
    },
    "naming": {
        "template": "{platform}_{title}_{date}",
        "sub_by_platform": True,
        "sub_by_date": False,
    },
    "network": {
        "proxy_mode": "system",  # system / none / custom
        "proxy_url": "",  # 自定义代理，如 http://127.0.0.1:7890
    },
    "general": {
        "theme": "auto",  # light / dark / auto
        "start_on_boot": False,
        "minimize_to_tray": True,
        "check_update": True,
    },
    "accounts": {
        "douyin": [],
        "kuaishou": [],
    },
    "completed_downloads": [],
    "favorites": [],
    "stats": {
        "total_count": 0,
        "total_size": 0,
        "today_count": 0,
        "today_size": 0,
        "today_date": "",
    },
}


class SettingsManager(QObject):
    settings_changed = Signal(str, object)  # key, value

    def __init__(self, filepath: str = None):
        super().__init__()
        if filepath is None:
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    '..', '..', 'settings.json')
        self._filepath = os.path.normpath(filepath)
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                merged = DEFAULT_SETTINGS.copy()
                self._deep_merge(merged, data)
                return merged
            except (json.JSONDecodeError, IOError):
                pass
        return DEFAULT_SETTINGS.copy()

    def _deep_merge(self, base: dict, override: dict):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def save(self):
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        with open(self._filepath, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, path: str, default=None):
        keys = path.split('.')
        value = self._data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        return value if value is not None else default

    def set(self, path: str, value):
        keys = path.split('.')
        target = self._data
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value
        self.save()
        self.settings_changed.emit(path, value)

    @property
    def save_path(self) -> str:
        return self.get('download.save_path')

    @property
    def max_concurrent(self) -> int:
        return self.get('download.max_concurrent', 3)

    @property
    def naming_template(self) -> str:
        return self.get('naming.template', '{platform}_{title}_{date}')

    @property
    def sub_by_platform(self) -> bool:
        return self.get('naming.sub_by_platform', True)

    @property
    def sub_by_date(self) -> bool:
        return self.get('naming.sub_by_date', False)

    @property
    def proxy_mode(self) -> str:
        return self.get('network.proxy_mode', 'system')

    @property
    def proxy_url(self) -> str:
        return self.get('network.proxy_url', '')
