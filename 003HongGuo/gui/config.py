"""应用配置管理 - JSON 文件读写"""
import json
import logging
from pathlib import Path

logger = logging.getLogger("hongguo")

CONFIG_FILE = Path(__file__).parent.parent / ".hongguo_config.json"

DEFAULTS = {
    "theme": "Light",
    "mica_enabled": False,
    "download_path": str(Path.home() / "Desktop"),
    "max_concurrent": 3,
    "max_retries": 3,
    "close_behavior": "exit",  # "exit" | "tray"
}


class ConfigManager:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self._load()

    def _load(self):
        if CONFIG_FILE.exists():
            try:
                loaded = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                # 迁移旧版本的中文配置值
                migrated = False
                theme_map = {"浅色": "Light", "深色": "Dark", "跟随系统": "System"}
                if loaded.get("theme") in theme_map:
                    loaded["theme"] = theme_map[loaded["theme"]]
                    migrated = True
                self._data.update(loaded)
                if migrated:
                    self._save()
            except json.JSONDecodeError:
                logger.exception("配置文件格式错误, 使用默认配置")
            except OSError:
                logger.exception("读取配置文件失败, 使用默认配置")

    def _save(self):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            logger.exception("保存配置文件失败")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        if self._data.get(key) != value:
            self._data[key] = value
            self._save()

    @property
    def theme(self) -> str:
        return self._data["theme"]

    @theme.setter
    def theme(self, value: str):
        self.set("theme", value)

    @property
    def mica_enabled(self) -> bool:
        return self._data["mica_enabled"]

    @mica_enabled.setter
    def mica_enabled(self, value: bool):
        self.set("mica_enabled", value)

    @property
    def download_path(self) -> str:
        return self._data["download_path"]

    @download_path.setter
    def download_path(self, value: str):
        self.set("download_path", value)

    @property
    def max_concurrent(self) -> int:
        return self._data["max_concurrent"]

    @max_concurrent.setter
    def max_concurrent(self, value: int):
        self.set("max_concurrent", value)

    @property
    def max_retries(self) -> int:
        return self._data["max_retries"]

    @max_retries.setter
    def max_retries(self, value: int):
        self.set("max_retries", value)

    @property
    def close_behavior(self) -> str:
        return self._data["close_behavior"]

    @close_behavior.setter
    def close_behavior(self, value: str):
        self.set("close_behavior", value)
