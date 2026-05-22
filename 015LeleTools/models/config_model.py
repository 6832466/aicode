"""
配置数据模型
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class APIEndpoint:
    """API 端点配置"""
    name: str
    base_url: str = ""
    api_key: str = ""
    model: str = "gemini-2.5-pro"
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "APIEndpoint":
        return cls(
            name=d.get("name", ""),
            base_url=d.get("base_url", ""),
            api_key=d.get("api_key", ""),
            model=d.get("model", "gemini-2.5-pro"),
            enabled=d.get("enabled", True),
        )
