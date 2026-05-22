"""CUDA Toolkit 与 cuDNN 推荐。"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from config import CUDA_DOWNLOAD_PAGE, CUDNN_DOWNLOAD_PAGE
from services.url_normalize import normalize_nvidia_url


@dataclass
class CudaPackage:
    version: str
    display_name: str
    download_url: str
    download_page: str
    note: str


@dataclass
class CudnnPackage:
    version: str
    display_name: str
    download_url: str
    download_page: str
    note: str


# 驱动支持的最高 CUDA 与推荐 Toolkit / cuDNN（随官方更新可调整）
_CUDA_MATRIX = [
    (13.0, "13.0", "https://developer.nvidia.com/cuda-13-0-0-download-archive"),
    (12.8, "12.8", "https://developer.nvidia.com/cuda-12-8-0-download-archive"),
    (12.6, "12.6", "https://developer.nvidia.com/cuda-12-6-0-download-archive"),
    (12.4, "12.4", "https://developer.nvidia.com/cuda-12-4-0-download-archive"),
    (12.1, "12.1", "https://developer.nvidia.com/cuda-12-1-0-download-archive"),
]

_CUDNN_MATRIX = [
    ("13.0", "9.10", "https://developer.nvidia.com/cudnn-downloads"),
    ("12.8", "9.10", "https://developer.nvidia.com/cudnn-downloads"),
    ("12.6", "9.6", "https://developer.nvidia.com/cudnn-downloads"),
    ("12.4", "9.5", "https://developer.nvidia.com/cudnn-downloads"),
]


def _parse_driver_cuda_max(cuda_driver_version: str) -> float:
    try:
        return float(cuda_driver_version)
    except ValueError:
        return 12.0


def _pick_cuda_toolkit(max_cuda: float, pytorch_cuda_tag: str = "") -> CudaPackage:
    if pytorch_cuda_tag:
        try:
            pt_major = int(pytorch_cuda_tag[:2])
            pt_minor = int(pytorch_cuda_tag[2:4]) if len(pytorch_cuda_tag) >= 4 else 0
            target = pt_major + pt_minor / 10.0
        except ValueError:
            target = max_cuda
    else:
        target = max_cuda

    chosen = _CUDA_MATRIX[-1]
    for threshold, version, page in _CUDA_MATRIX:
        if max_cuda >= threshold - 0.01 or target >= threshold - 0.01:
            chosen = (threshold, version, page)
            break

    _, version, page = chosen
    # 归档页路径易变，统一使用官方下载向导（实测可访问）
    return CudaPackage(
        version=version,
        display_name=f"CUDA Toolkit {version}",
        download_url=CUDA_DOWNLOAD_PAGE,
        download_page=normalize_nvidia_url(page) if _archive_page_ok(page) else CUDA_DOWNLOAD_PAGE,
        note=(
            "仅在使用需要系统级 CUDA 的软件（自编译、TensorRT 等）时需要安装。"
            "若仅通过 pip 安装 PyTorch，可跳过此步（PyTorch 自带 CUDA 运行时）。"
        ),
    )


def _archive_page_ok(url: str) -> bool:
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return False
        text = resp.text[:4000].lower()
        return "404" not in text or "page not found" not in text
    except Exception:
        return False


def _pick_cudnn(cuda_version: str) -> CudnnPackage:
    major_minor = cuda_version
    cudnn_ver = "9.x"
    page = CUDNN_DOWNLOAD_PAGE
    for cv, cv_ver, cv_page in _CUDNN_MATRIX:
        if cv == major_minor or major_minor.startswith(cv.rsplit(".", 1)[0]):
            cudnn_ver = cv_ver
            page = cv_page
            break
    return CudnnPackage(
        version=cudnn_ver,
        display_name=f"cuDNN {cudnn_ver}（for CUDA {cuda_version}）",
        download_url=page,
        download_page=CUDNN_DOWNLOAD_PAGE,
        note=(
            "需先安装对应版本的 CUDA Toolkit，再安装 cuDNN。"
            "NVIDIA 开发者网站需登录后下载，请在页面选择匹配的 CUDA 版本。"
        ),
    )


def fetch_cuda_cudnn(
    cuda_driver_version: str,
    pytorch_cuda_tag: str = "",
) -> tuple[CudaPackage, CudnnPackage]:
    max_cuda = _parse_driver_cuda_max(cuda_driver_version)
    cuda_pkg = _pick_cuda_toolkit(max_cuda, pytorch_cuda_tag)
    cudnn_pkg = _pick_cudnn(cuda_pkg.version)
    return cuda_pkg, cudnn_pkg


def scrape_latest_cuda_hint() -> str:
    try:
        resp = requests.get(
            "https://developer.nvidia.com/cuda-downloads",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        versions = re.findall(r"CUDA Toolkit (\d+\.\d+(?:\.\d+)?)", resp.text)
        if versions:
            return versions[-1]
    except Exception:
        pass
    return ""
