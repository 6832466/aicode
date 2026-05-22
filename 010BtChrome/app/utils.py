from __future__ import annotations

from urllib.parse import urlparse


def extract_rows(data: dict | None) -> list:
    """安全获取 API 响应中的行列表，兼容 list/rows 两种键名"""
    if not data:
        return []
    return data.get("list") or data.get("rows", [])


def extract_total(data: dict | None, fallback: int = 0) -> int:
    """安全获取 API 响应中的总数，兼容 totalNum/total 两种键名"""
    if not data:
        return fallback
    val = data.get("totalNum")
    if val is not None:
        return val
    return data.get("total", fallback)


def proxy_type_label(t: str | None) -> str:
    """将代理类型枚举值转为用户可读的显示文本"""
    return t.upper() if t and t != "noproxy" else "无代理"


def short_str(s: str, max_len: int) -> str:
    """截断字符串，过长时末尾加 …"""
    return s if len(s) <= max_len else s[: max_len - 3] + "…"


def extract_host(url: str) -> str:
    """从 URL 中提取域名（用于 platformIcon）"""
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.hostname or url
