"""
配置读写管理器 — JSON 配置文件
"""

import json
import logging
from typing import Optional

from app.constants import config_path
from models.config_model import APIEndpoint

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = {
    "api": {
        "default_endpoint": "",
        "timeout": 60,
        "auto_save_records": True,
        "endpoints": [],
    },
    "ui": {
        "theme": "light",
        "accent_color": "#2ecc71",
        "font_family": "Microsoft YaHei",
        "font_size": 14,
    },
    "proxy": {
        "enabled": False,
        "http_proxy": "",
        "https_proxy": "",
    },
    "chat": {
        "max_context_messages": 20,
        "system_prompt": "你是一个专业的文本处理助手，擅长改写文章、推荐BGM、生成爆款开头。",
    },
    "processing": {
        "default_segment_size": 1500,
        "default_model": "gemini-2.5-pro",
        "stream_output": True,
    },
}


class ConfigManager:
    """JSON 配置管理器（单例）"""

    _instance: Optional["ConfigManager"] = None

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        self._loaded = True
        self._path = config_path()
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = _DEFAULT_CONFIG.copy()
                _deep_merge(merged, data)
                return merged
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("配置文件加载失败: %s，使用默认配置", e)
        return _DEFAULT_CONFIG.copy()

    def save(self):
        """保存配置到文件"""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("保存配置失败: %s", e)

    # ── API 端点管理 ──

    def get_endpoints(self) -> list[APIEndpoint]:
        return [APIEndpoint.from_dict(d) for d in self._data["api"]["endpoints"]]

    def get_endpoint(self, name: str) -> Optional[APIEndpoint]:
        for d in self._data["api"]["endpoints"]:
            if d["name"] == name:
                return APIEndpoint.from_dict(d)
        return None

    def get_default_endpoint(self) -> Optional[APIEndpoint]:
        name = self._data["api"]["default_endpoint"]
        if name:
            return self.get_endpoint(name)
        endpoints = self.get_endpoints()
        return endpoints[0] if endpoints else None

    def add_or_update_endpoint(self, endpoint: APIEndpoint):
        """添加或更新端点"""
        for i, d in enumerate(self._data["api"]["endpoints"]):
            if d["name"] == endpoint.name:
                self._data["api"]["endpoints"][i] = endpoint.to_dict()
                self.save()
                return
        self._data["api"]["endpoints"].append(endpoint.to_dict())
        self.save()

    def delete_endpoint(self, name: str):
        self._data["api"]["endpoints"] = [
            d for d in self._data["api"]["endpoints"] if d["name"] != name
        ]
        if self._data["api"]["default_endpoint"] == name:
            self._data["api"]["default_endpoint"] = ""
        self.save()

    def set_default_endpoint(self, name: str):
        self._data["api"]["default_endpoint"] = name
        self.save()

    # ── API 通用设置 ──

    def get(self, section: str, key: str, default=None):
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value):
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value
        self.save()

    @property
    def timeout(self) -> int:
        return self._data["api"]["timeout"]

    @property
    def auto_save_records(self) -> bool:
        return self._data["api"]["auto_save_records"]

    @property
    def proxy_enabled(self) -> bool:
        return self._data["proxy"]["enabled"]

    @property
    def http_proxy(self) -> str:
        return self._data["proxy"]["http_proxy"]

    @property
    def https_proxy(self) -> str:
        return self._data["proxy"]["https_proxy"]

    @property
    def theme(self) -> str:
        return self._data["ui"]["theme"]

    @property
    def default_model(self) -> str:
        return self._data["processing"]["default_model"]

    @property
    def default_segment_size(self) -> int:
        return self._data["processing"]["default_segment_size"]

    @property
    def stream_output(self) -> bool:
        return self._data["processing"]["stream_output"]


def _deep_merge(base: dict, override: dict):
    """递归合并 override 到 base"""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
