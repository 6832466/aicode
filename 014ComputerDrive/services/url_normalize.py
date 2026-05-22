"""将 NVIDIA 链接规范为当前可访问的地址（国内优先 nvidia.cn）。"""
from __future__ import annotations

import re


def normalize_nvidia_url(url: str) -> str:
    if not url or not url.strip():
        return url
    u = url.strip()

    # 已失效的 Studio 旧路径 → 驱动首页（具体 Studio 详情由 driver_service 动态生成）
    u = u.replace("www.nvidia.cn/studio/drivers/", "www.nvidia.cn/drivers/")
    u = u.replace("www.nvidia.com/zh-cn/studio/drivers/", "www.nvidia.cn/drivers/")
    u = u.replace("www.nvidia.com/studio/drivers/", "www.nvidia.cn/drivers/")

    # zh-cn 路径在浏览器中常跳转到 404 的 studio/drivers，统一为 nvidia.cn
    u = re.sub(
        r"https?://www\.nvidia\.com/zh-cn/",
        "https://www.nvidia.cn/",
        u,
        flags=re.IGNORECASE,
    )
    u = re.sub(
        r"https?://www\.nvidia\.com/en-us/",
        "https://www.nvidia.cn/",
        u,
        flags=re.IGNORECASE,
    )

    # 手动查找 /lookup 会跳到驱动首页，直接用首页
    if "/drivers/lookup" in u.lower():
        return "https://www.nvidia.cn/drivers/"

    return u


def driver_details_url(download_id: str) -> str:
    return f"https://www.nvidia.cn/drivers/details/{download_id}/"


def driver_process_find_studio(pfid: str, psid: str, os_id: str = "135") -> str:
    return (
        "https://www.nvidia.com/Download/processFind.aspx"
        f"?dtcid=1&lang=cn&lid=1&osid={os_id}&pfid={pfid}&psid={psid}&whql=4"
    )
