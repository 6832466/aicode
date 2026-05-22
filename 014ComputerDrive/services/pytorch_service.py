"""PyTorch 版本与 pip / wheel 下载推荐。"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass

import requests

from config import PYTORCH_GET_STARTED, PYTORCH_WHEEL_INDEX


@dataclass
class PyTorchPackage:
    torch_version: str
    cuda_tag: str
    python_tag: str
    pip_command: str
    wheel_url: str
    index_url: str
    download_page: str
    note: str


def _python_tag() -> str:
    ver = sys.version_info
    return f"cp{ver.major}{ver.minor}"


def _score_version(ver: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in ver.split("."))
    except ValueError:
        return (0,)


def _compute_capability_to_cuda_tag(cc: str) -> list[str]:
    """根据算力推荐优先尝试的 PyTorch CUDA 标签。"""
    try:
        major = int(cc.split(".")[0])
    except (ValueError, IndexError):
        major = 8
    if major >= 12:
        return ["130", "129", "128", "126"]
    if major >= 9:
        return ["126", "124", "121"]
    if major >= 8:
        return ["124", "121", "118"]
    return ["121", "118"]


def _find_best_wheel(python_tag: str, cuda_candidates: list[str]) -> tuple[str, str, str] | None:
    try:
        resp = requests.get(PYTORCH_WHEEL_INDEX, timeout=25)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return None

    best: tuple[tuple[int, ...], str, str, str] | None = None
    for cu in cuda_candidates:
        pattern = rf"torch-([\d.]+)\+cu{cu}-{python_tag}-{python_tag}-win_amd64\.whl"
        versions = re.findall(pattern, html)
        if not versions:
            continue
        ver = max(versions, key=_score_version)
        candidate = (_score_version(ver), ver, cu, f"cu{cu}")
        if best is None or candidate[0] > best[0]:
            best = candidate

    if not best:
        return None
    _, torch_ver, cu_num, cuda_tag = best
    wheel = (
        f"https://download.pytorch.org/whl/{cuda_tag}/"
        f"torch-{torch_ver}+{cuda_tag}-{python_tag}-{python_tag}-win_amd64.whl"
    )
    return torch_ver, cuda_tag, wheel


def fetch_pytorch(compute_capability: str = "", cuda_driver_version: str = "") -> PyTorchPackage:
    python_tag = _python_tag()
    cuda_candidates = _compute_capability_to_cuda_tag(compute_capability)

    if cuda_driver_version:
        try:
            drv = float(cuda_driver_version)
            if drv >= 13.0:
                for tag in ("130", "129", "128"):
                    if tag not in cuda_candidates:
                        cuda_candidates.insert(0, tag)
        except ValueError:
            pass

    found = _find_best_wheel(python_tag, cuda_candidates)
    if found:
        torch_ver, cuda_tag, wheel_url = found
    else:
        torch_ver, cuda_tag, wheel_url = "2.x", "cu126", ""
        cuda_candidates = ["126"]

    index_url = f"https://download.pytorch.org/whl/{cuda_tag}"
    pip_cmd = (
        f"pip install torch torchvision torchaudio "
        f"--index-url {index_url}"
    )

    return PyTorchPackage(
        torch_version=torch_ver,
        cuda_tag=cuda_tag,
        python_tag=python_tag,
        pip_command=pip_cmd,
        wheel_url=wheel_url,
        index_url=index_url,
        download_page=PYTORCH_GET_STARTED,
        note=(
            "PyTorch 官方 wheel 已捆绑 CUDA 运行时，一般无需单独安装 CUDA/cuDNN。"
            f"当前检测 Python 标签: {python_tag}。"
            "安装后可用 python -c \"import torch; print(torch.cuda.is_available())\" 验证。"
        ),
    )
