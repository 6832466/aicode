"""API 配置持久化 —— 基于 QFluentWidgets QConfig + 关键字段直接读写 JSON。"""

import json

from qfluentwidgets import QConfig, ConfigItem

API_PRESETS = {
    "bj.nfai.lol": {
        "name": "豹剪 API (bj.nfai.lol)",
        "url": "https://bj.nfai.lol/pg",
        "key": "sk-z4dG67AlByr2vfabt7GMo98XG5CHBjMmSFCQFNF9HLAzRip0",
        "model": "gpt-image-2",
        "path": "/chat/completions",
        "user_id": "13679",
        "group": "default",
    },
}

MODEL_CHOICES = [
    ("gpt-image-2 — $0.042/次", "gpt-image-2"),
    ("gpt-image-2-1k — $0.042/次", "gpt-image-2-1k"),
    ("gpt-image-2-2k — $0.082/次", "gpt-image-2-2k"),
    ("gpt-image-2-4k — $0.082/次", "gpt-image-2-4k"),
    ("gemini-2.5-pro — 文本对话", "gemini-2.5-pro"),
]


class ApiConfig(QConfig):
    """全局 API 配置，自动持久化到本地 JSON。"""

    api_base_url = ConfigItem("Api", "BaseUrl", "")
    api_key = ConfigItem("Api", "Key", "sk-z4dG67AlByr2vfabt7GMo98XG5CHBjMmSFCQFNF9HLAzRip0")
    api_endpoint_path = ConfigItem("Api", "EndpointPath", "/chat/completions")
    api_session_cookie = ConfigItem("Api", "SessionCookie", "")
    api_user_id = ConfigItem("Api", "UserId", "13679")
    model_name = ConfigItem("Api", "ModelName", "gpt-image-2")
    remote_preset = ConfigItem("Api", "RemotePreset", "bj.nfai.lol")
    img_prefix = ConfigItem("Prompt", "ImgPrefix", "")
    img_suffix = ConfigItem("Prompt", "ImgSuffix", "")
    vid_prefix = ConfigItem("Prompt", "VidPrefix", "")
    vid_suffix = ConfigItem("Prompt", "VidSuffix", "")
    img_save_dir = ConfigItem("Api", "ImgSaveDir", "")


# ── 配置读写辅助（统一通过 QConfig，避免双写竞争）──

def get_session_cookie() -> str:
    return api_config.api_session_cookie.value


def set_session_cookie(value: str) -> None:
    api_config.api_session_cookie.value = value


def get_user_id() -> str:
    """从配置中提取纯数字 user ID（兼容 JSON 对象与纯数字字符串）。"""
    raw = api_config.api_user_id.value
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return str(obj.get("id", 13679))
        return str(obj)
    except (json.JSONDecodeError, TypeError):
        return str(raw)


def set_user_id(value: str) -> None:
    api_config.api_user_id.value = value


def get_img_save_dir() -> str:
    return api_config.img_save_dir.value


def set_img_save_dir(value: str) -> None:
    api_config.img_save_dir.value = value


# 全局单例
api_config = ApiConfig()

