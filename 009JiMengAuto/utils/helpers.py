"""工具函数和常量"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 素材限制（按需求文档）
MATERIAL_LIMITS = {
    "image": {"max_count": 9, "max_size_mb": 30},
    "audio": {"max_count": 3, "max_size_mb": 15},
    "video": {"max_count": 3, "max_size_mb": 50},
}

# 支持的视频比例（按需求文档）
ASPECT_RATIOS = ["16:9", "9:16", "1:1", "4:3"]

# 分辨率
RESOLUTIONS = ["720p", "1080p"]

# 时长范围（按需求文档：5~15秒）
DURATION_RANGE = (5, 15)
DURATION_OPTIONS = [5, 10, 12, 13, 14, 15]

# 素材类型与扩展名映射
MATERIAL_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".bmp"},
    "audio": {".wav", ".mp3", ".aac", ".flac", ".ogg"},
    "video": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
}


def app_root() -> Path:
    """获取应用根目录（兼容 PyInstaller frozen 模式）"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def generate_filename(seq: int, scene: str, ext: str = ".mp4") -> str:
    """生成下载文件名：{序号}_{场次}_{时间戳}.mp4
    例：001_第1场_20260515_202148.mp4
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{seq:03d}_{scene}_{ts}{ext}"


def infer_material_type(file_path: str) -> str:
    """根据文件路径推断素材类型：image/audio/video"""
    ext = Path(file_path).suffix.lower()
    for mtype, exts in MATERIAL_EXTENSIONS.items():
        if ext in exts:
            return mtype
    return "unknown"


def validate_material(file_path: str) -> tuple[bool, str]:
    """验证素材文件存在且在大小限制内"""
    p = Path(file_path)
    if not p.exists():
        return False, f"文件不存在: {file_path}"
    mtype = infer_material_type(file_path)
    limit = MATERIAL_LIMITS.get(mtype)
    if limit:
        size_mb = p.stat().st_size / (1024 * 1024)
        if size_mb > limit["max_size_mb"]:
            return False, f"{mtype}文件超过大小限制({limit['max_size_mb']}MB): {file_path}"
    return True, ""


def validate_duration(duration: int) -> tuple[bool, str]:
    """验证时长是否在范围内（5~15秒）"""
    if duration < DURATION_RANGE[0] or duration > DURATION_RANGE[1]:
        return False, f"时长 {duration} 秒超出范围（{DURATION_RANGE[0]}~{DURATION_RANGE[1]}秒）"
    return True, ""


def validate_ratio(ratio: str) -> tuple[bool, str]:
    """验证比例是否合法"""
    if ratio not in ASPECT_RATIOS:
        return False, f"比例 '{ratio}' 无效，合法值：{', '.join(ASPECT_RATIOS)}"
    return True, ""


def parse_ratio(raw: str) -> str:
    """解析比例，处理 Excel 中可能的时间格式 09:16:00 → 9:16"""
    if not raw:
        return "16:9"
    raw = str(raw).strip()
    if ":" in raw:
        parts = raw.split(":")
        if len(parts) == 3:
            # 时间格式 09:16:00 → 9:16
            h, w, _ = parts
            ratio = f"{int(h)}:{int(w)}"
            if ratio in ASPECT_RATIOS:
                return ratio
        elif len(parts) == 2:
            # 已经是比例格式
            try:
                ratio = f"{int(parts[0])}:{int(parts[1])}"
                if ratio in ASPECT_RATIOS:
                    return ratio
            except ValueError:
                pass
    # 尝试直接匹配
    for r in ASPECT_RATIOS:
        if r in raw or raw in r:
            return r
    return "16:9"


def extract_scene_number(text: str) -> Optional[str]:
    """从文本中提取场次名称，如 '第1场'"""
    m = re.search(r"第(\d+)场", text)
    if m:
        return f"第{m.group(1)}场"
    return None


def format_file_size(bytes_num: int) -> str:
    """格式化文件大小"""
    if bytes_num < 1024:
        return f"{bytes_num}B"
    elif bytes_num < 1024 * 1024:
        return f"{bytes_num/1024:.1f}KB"
    else:
        return f"{bytes_num/(1024*1024):.1f}MB"


def truncate_text(text: str, max_len: int = 50) -> str:
    """截断文本，用于表格显示"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def get_file_info(file_path: str) -> dict:
    """获取文件基本信息"""
    p = Path(file_path)
    if not p.exists():
        return {"exists": False, "path": file_path}
    size = p.stat().st_size
    return {
        "exists": True,
        "path": file_path,
        "name": p.name,
        "size": size,
        "size_text": format_file_size(size),
        "ext": p.suffix.lower(),
        "type": infer_material_type(file_path),
    }