"""查询 NVIDIA 显卡驱动下载信息。"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

import requests

from config import (
    DRIVER_API_URL,
    DRIVERS_HOME_CN,
    LANG_CODE_ZH_CN,
    OS_ID_WIN11_64,
    PROCESS_FIND_BASE,
    STUDIO_INFO_CN,
)
from services.catalog import resolve_pfid
from services.gpu_detector import GpuInfo
from services.url_normalize import (
    driver_details_url,
    driver_process_find_studio,
    normalize_nvidia_url,
)


@dataclass
class DriverPackage:
    name: str
    version: str
    display_version: str
    download_url: str
    file_size: str
    release_date: str
    details_url: str
    driver_type: str
    note: str = ""


def _decode(value: str) -> str:
    return urllib.parse.unquote(value or "").replace("+", " ")


def _parse_driver_entry(info: dict, driver_type: str) -> DriverPackage | None:
    if not info or info.get("Success") != "1":
        return None
    url = normalize_nvidia_url(info.get("DownloadURL") or "")
    if not url:
        return None
    details = normalize_nvidia_url(info.get("DetailsURL") or "")
    return DriverPackage(
        name=_decode(info.get("NameLocalized") or info.get("Name") or ""),
        version=info.get("Version") or "",
        display_version=info.get("DisplayVersion") or "",
        download_url=url,
        file_size=info.get("DownloadURLFileSize") or "",
        release_date=info.get("ReleaseDateTime") or "",
        details_url=details,
        driver_type=driver_type,
    )


def _query_api(pfid: str, dltype: str = "1", count: int = 3) -> list[dict]:
    params = {
        "func": "DriverManualLookup",
        "pfid": pfid,
        "psid": pfid,
        "osID": OS_ID_WIN11_64,
        "languageCode": LANG_CODE_ZH_CN,
        "isWHQL": "1",
        "dch": "1",
        "beta": "null",
        "dltype": dltype,
        "numberOfResults": str(count),
        "gfeExclusive": "0",
        "webExclusive": "0",
    }
    resp = requests.get(DRIVER_API_URL, params=params, timeout=25)
    resp.raise_for_status()
    payload = resp.json()
    return [item.get("downloadInfo", {}) for item in payload.get("IDS", [])]


def _fetch_studio_details_id(pfid: str, psid: str | None = None) -> str:
    """从 NVIDIA processFind（dtcid=1 = Studio）解析最新驱动详情 ID。"""
    psid = psid or pfid
    try:
        resp = requests.get(
            PROCESS_FIND_BASE,
            params={
                "dtcid": "1",
                "lang": "cn",
                "lid": "1",
                "osid": OS_ID_WIN11_64,
                "pfid": pfid,
                "psid": psid,
                "whql": "4",
            },
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        resp.raise_for_status()
        match = re.search(r"driverResults\.aspx/(\d+)", resp.text, re.IGNORECASE)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""


def fetch_driver_recommendation(
    gpu: GpuInfo, catalog: dict | None = None
) -> tuple[str, str, str]:
    """返回 (显示名称, 版本号, 下载链接)。"""
    pfid, product, _ = resolve_pfid(gpu, catalog)
    if not pfid:
        return "显卡驱动", "", DRIVERS_HOME_CN

    try:
        entries = _query_api(pfid, count=1)
    except Exception:
        return "显卡驱动", "", DRIVERS_HOME_CN

    gr = _parse_driver_entry(entries[0], "Game Ready") if entries else None
    if gr and gr.download_url:
        return f"GeForce 驱动 ({product or gpu.name})", gr.version, gr.download_url

    studio_id = _fetch_studio_details_id(pfid)
    if studio_id:
        url = driver_details_url(studio_id)
        ver = gr.version if gr else ""
        return f"显卡驱动 ({product or gpu.name})", ver, url

    return "显卡驱动", "", driver_process_find_studio(pfid) if pfid else DRIVERS_HOME_CN


def fetch_drivers(gpu: GpuInfo, catalog: dict | None = None) -> tuple[list[DriverPackage], str, str]:
    pfid, product, _segment = resolve_pfid(gpu, catalog)
    if not pfid:
        return [], "", ""

    packages: list[DriverPackage] = []
    game_ready: DriverPackage | None = None

    try:
        entries = _query_api(pfid)
    except Exception as exc:
        raise RuntimeError(f"驱动查询失败: {exc}") from exc

    if entries:
        game_ready = _parse_driver_entry(entries[0], "Game Ready")
        if game_ready:
            game_ready.note = "游戏、办公与通用场景；创作类用途请选 Studio 驱动。"
            packages.append(game_ready)

    studio_id = _fetch_studio_details_id(pfid)
    gr = game_ready
    if studio_id:
        studio_url = driver_details_url(studio_id)
        studio = DriverPackage(
            name="NVIDIA Studio Driver（创作 / 剪辑）",
            version=gr.version if gr else "",
            display_version=gr.display_version if gr else "",
            download_url=studio_url,
            file_size=gr.file_size if gr else "",
            release_date=gr.release_date if gr else "",
            details_url=studio_url,
            driver_type="Studio",
            note=(
                "打开后在页面点击「下载」获取 Studio 安装包。"
                "专为 Premiere、DaVinci Resolve、After Effects 等创作软件优化。"
            ),
        )
    else:
        studio = DriverPackage(
            name="NVIDIA Studio Driver（创作 / 剪辑）",
            version=gr.version if gr else "",
            display_version=gr.display_version if gr else "",
            download_url=driver_process_find_studio(pfid),
            file_size="",
            release_date=gr.release_date if gr else "",
            details_url=driver_process_find_studio(pfid),
            driver_type="Studio",
            note="在列表中选择最新 Studio Driver，进入详情页后点击下载。",
        )

    packages.insert(0, studio)

    manual = DriverPackage(
        name="驱动手动查找（备用）",
        version="",
        display_version="",
        download_url=DRIVERS_HOME_CN,
        file_size="",
        release_date="",
        details_url=DRIVERS_HOME_CN,
        driver_type="Manual",
        note=f"在页面手动选择产品类型与型号：{product or gpu.name}",
    )
    packages.append(manual)

    return packages, product, pfid
