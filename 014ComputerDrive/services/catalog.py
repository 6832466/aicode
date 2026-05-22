"""GPU 型号与 NVIDIA pfid 映射。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from config import GPU_CATALOG_PATH, GPU_CATALOG_URL
from services.gpu_detector import GpuInfo, normalize_gpu_name


def _load_local_catalog() -> dict:
    if not GPU_CATALOG_PATH.is_file():
        return {"desktop": {}, "notebook": {}}
    with GPU_CATALOG_PATH.open(encoding="utf-8") as fp:
        return json.load(fp)


def _fetch_remote_catalog() -> dict | None:
    try:
        resp = requests.get(GPU_CATALOG_URL, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def get_catalog() -> dict:
    remote = _fetch_remote_catalog()
    if remote:
        return remote
    return _load_local_catalog()


def _best_match(name: str, mapping: dict[str, str]) -> tuple[str, str] | None:
    normalized = normalize_gpu_name(name)
    if normalized in mapping:
        return normalized, mapping[normalized]

    lower = normalized.lower()
    candidates: list[tuple[int, str, str]] = []
    for product, pfid in mapping.items():
        pl = product.lower()
        if pl in lower or lower in pl:
            score = len(pl)
            candidates.append((score, product, pfid))
    if candidates:
        candidates.sort(reverse=True)
        _, product, pfid = candidates[0]
        return product, pfid

    nums = re.findall(r"\d{3,4}", normalized)
    if nums:
        for product, pfid in mapping.items():
            if any(n in product for n in nums) and "rtx" in product.lower() and "rtx" in lower:
                return product, pfid
    return None


def resolve_pfid(gpu: GpuInfo, catalog: dict | None = None) -> tuple[str, str, str]:
    """
    返回 (pfid, matched_product_name, segment)。
    segment: desktop | notebook
    """
    catalog = catalog or get_catalog()
    segment = "notebook" if gpu.is_notebook else "desktop"
    mapping = catalog.get(segment) or {}
    match = _best_match(gpu.name, mapping)
    if match:
        return match[1], match[0], segment

    other = catalog.get("desktop" if segment == "notebook" else "notebook") or {}
    match = _best_match(gpu.name, other)
    if match:
        return match[1], match[0], "desktop" if segment == "notebook" else "notebook"
    return "", "", segment
