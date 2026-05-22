"""根据本机显卡生成四项推荐。"""
from __future__ import annotations

from dataclasses import dataclass

from services.catalog import get_catalog
from services.cuda_service import fetch_cuda_cudnn
from services.driver_service import fetch_driver_recommendation
from services.gpu_detector import DetectionResult, GpuInfo
from services.pytorch_service import fetch_pytorch


@dataclass
class ComponentRec:
    name: str
    version: str
    download_url: str
    copy_text: str = ""


@dataclass
class RecommendationBundle:
    gpu: GpuInfo
    matched_product: str
    driver: ComponentRec
    cuda: ComponentRec
    cudnn: ComponentRec
    pytorch: ComponentRec


def build_recommendations(detection: DetectionResult) -> RecommendationBundle:
    gpu = detection.primary
    if not gpu:
        raise ValueError("未检测到 NVIDIA 显卡")

    catalog = get_catalog()
    from services.catalog import resolve_pfid

    _, drv_ver, drv_url = fetch_driver_recommendation(gpu, catalog)
    _, product, _ = resolve_pfid(gpu, catalog)

    pytorch = fetch_pytorch(gpu.compute_capability, gpu.cuda_driver_version)
    cuda_tag = pytorch.cuda_tag.replace("cu", "")
    cuda_pkg, cudnn_pkg = fetch_cuda_cudnn(gpu.cuda_driver_version, cuda_tag)

    pt_url = pytorch.wheel_url or pytorch.index_url

    return RecommendationBundle(
        gpu=gpu,
        matched_product=product,
        driver=ComponentRec(
            name="显卡驱动",
            version=drv_ver or "最新",
            download_url=drv_url,
            copy_text=drv_url,
        ),
        cuda=ComponentRec(
            name="CUDA Toolkit",
            version=cuda_pkg.version,
            download_url=cuda_pkg.download_url,
            copy_text=cuda_pkg.download_url,
        ),
        cudnn=ComponentRec(
            name="cuDNN",
            version=cudnn_pkg.version,
            download_url=cudnn_pkg.download_url,
            copy_text=cudnn_pkg.download_url,
        ),
        pytorch=ComponentRec(
            name="PyTorch",
            version=f"{pytorch.torch_version} ({pytorch.cuda_tag})",
            download_url=pt_url,
            copy_text=pytorch.pip_command,
        ),
    )
