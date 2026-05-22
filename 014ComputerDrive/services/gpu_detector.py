"""检测本机 NVIDIA 显卡信息。"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

try:
    import pynvml
except ImportError:
    pynvml = None


@dataclass
class GpuInfo:
    index: int
    name: str
    driver_version: str = ""
    vram_total_mb: int = 0
    vram_used_mb: int = 0
    cuda_driver_version: str = ""
    compute_capability: str = ""
    is_notebook: bool = False


@dataclass
class DetectionResult:
    gpus: list[GpuInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def primary(self) -> GpuInfo | None:
        return self.gpus[0] if self.gpus else None


def _format_cuda_version(raw: int) -> str:
    major = raw // 1000
    minor = (raw % 1000) // 10
    return f"{major}.{minor}"


def _format_compute_cap(major: int, minor: int) -> str:
    return f"{major}.{minor}"


def _detect_via_pynvml() -> DetectionResult:
    result = DetectionResult()
    if pynvml is None:
        result.errors.append("未安装 pynvml 库")
        return result
    try:
        pynvml.nvmlInit()
        driver = pynvml.nvmlSystemGetDriverVersion()
        if isinstance(driver, bytes):
            driver = driver.decode("utf-8", errors="replace")
        cuda_raw = pynvml.nvmlSystemGetCudaDriverVersion()
        cuda_str = _format_cuda_version(cuda_raw)
        count = pynvml.nvmlDeviceGetCount()
        for idx in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            cc_major, cc_minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
            result.gpus.append(
                GpuInfo(
                    index=idx,
                    name=name.strip(),
                    driver_version=str(driver).strip(),
                    vram_total_mb=int(mem.total // (1024 * 1024)),
                    vram_used_mb=int(mem.used // (1024 * 1024)),
                    cuda_driver_version=cuda_str,
                    compute_capability=_format_compute_cap(cc_major, cc_minor),
                    is_notebook=_guess_notebook(name),
                )
            )
    except Exception as exc:
        result.errors.append(f"NVML 检测失败: {exc}")
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    return result


def _detect_via_nvidia_smi() -> DetectionResult:
    result = DetectionResult()
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,driver_version,memory.total,memory.used,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except FileNotFoundError:
        result.errors.append("未找到 nvidia-smi，请确认已安装 NVIDIA 驱动")
        return result
    except Exception as exc:
        result.errors.append(f"nvidia-smi 执行失败: {exc}")
        return result

    if proc.returncode != 0:
        result.errors.append(proc.stderr.strip() or "nvidia-smi 返回错误")
        return result

    for line in proc.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        idx = int(parts[0]) if parts[0].isdigit() else len(result.gpus)
        name = parts[1]
        driver = parts[2] if len(parts) > 2 else ""
        vram_total = int(float(parts[3])) if len(parts) > 3 and parts[3] else 0
        vram_used = int(float(parts[4])) if len(parts) > 4 and parts[4] else 0
        cc = parts[5] if len(parts) > 5 else ""
        result.gpus.append(
            GpuInfo(
                index=idx,
                name=name,
                driver_version=driver,
                vram_total_mb=vram_total,
                vram_used_mb=vram_used,
                compute_capability=cc,
                is_notebook=_guess_notebook(name),
            )
        )
    return result


def _guess_notebook(name: str) -> bool:
    lower = name.lower()
    return "laptop" in lower or "mobile" in lower or "notebook" in lower or "max-q" in lower


def detect_gpus() -> DetectionResult:
    """优先 NVML，失败则回退 nvidia-smi。"""
    result = _detect_via_pynvml()
    if result.gpus:
        if not result.primary or not result.primary.cuda_driver_version:
            smi = _detect_via_nvidia_smi()
            if smi.gpus and result.primary:
                result.primary.cuda_driver_version = smi.primary.cuda_driver_version if smi.primary else ""
        return result
    smi = _detect_via_nvidia_smi()
    if smi.gpus:
        return smi
    if not result.errors:
        result.errors.extend(smi.errors)
    elif smi.errors:
        result.errors.extend(smi.errors)
    return result


def normalize_gpu_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name.strip())
    for prefix in ("NVIDIA ", "nVIDIA "):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    return name
