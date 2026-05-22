"""ConfigManager - load, merge defaults, save config.json."""
import json
import os
import sys
from typing import Any

DEFAULTS: dict[str, Any] = {
    "theme": "鎏金",
    "refresh_interval": 5,
    "opacity": 0.85,
    "au_threshold_upper": 0.0,
    "au_threshold_lower": 0.0,
    "xau_threshold_upper": 0.0,
    "xau_threshold_lower": 0.0,
    "volatility_window_minutes": 5,
    "volatility_threshold_pct": 1.0,
    "alert_cooldown_seconds": 60,
    "autostart": False,
    "window_x": -1,
    "window_y": -1,
}

if getattr(sys, 'frozen', False):
    # Running as PyInstaller exe — config next to the exe
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


class ConfigManager:
    def __init__(self, path: str = CONFIG_PATH):
        self._path = path
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                for k, v in DEFAULTS.items():
                    if k in stored:
                        self._data[k] = stored[k]
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key in DEFAULTS:
            self._data[key] = value
            self.save()

    def update(self, updates: dict[str, Any]) -> None:
        for k, v in updates.items():
            if k in DEFAULTS:
                self._data[k] = v
        self.save()

    @property
    def data(self) -> dict[str, Any]:
        return dict(self._data)

    def save_window_position(self, x: int, y: int) -> None:
        self._data["window_x"] = x
        self._data["window_y"] = y
        self.save()

    def get_window_position(self) -> tuple[int, int]:
        return self._data.get("window_x", -1), self._data.get("window_y", -1)
