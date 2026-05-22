"""共享配置与路径。"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
ICON_CANDIDATES = (
    PROJECT_ROOT / "1.ico",
    APP_DIR / "1.ico",
)
DATA_DIR = APP_DIR / "data"
GPU_CATALOG_PATH = DATA_DIR / "gpu_catalog.json"

DRIVER_API_URL = (
    "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/"
    "AjaxDriverService.php"
)
GPU_CATALOG_URL = (
    "https://raw.githubusercontent.com/ZenitH-AT/nvidia-data/main/gpu-data.json"
)

OS_ID_WIN11_64 = "135"
LANG_CODE_ZH_CN = "2052"

# 经实测可访问的 NVIDIA 中国站链接（勿使用 studio/drivers，会 404）
DRIVERS_HOME_CN = "https://www.nvidia.cn/drivers/"
STUDIO_INFO_CN = "https://www.nvidia.cn/studio/"
PROCESS_FIND_BASE = "https://www.nvidia.com/Download/processFind.aspx"

CUDA_DOWNLOAD_PAGE = "https://developer.nvidia.com/cuda-downloads"
CUDNN_DOWNLOAD_PAGE = "https://developer.nvidia.com/cudnn-downloads"
PYTORCH_GET_STARTED = "https://pytorch.org/get-started/locally/"
PYTORCH_WHEEL_INDEX = "https://download.pytorch.org/whl/torch/"

CONTACT_HINT = "rpalele"


def app_icon_path() -> Path | None:
    for path in ICON_CANDIDATES:
        if path.is_file():
            return path
    return None


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)
