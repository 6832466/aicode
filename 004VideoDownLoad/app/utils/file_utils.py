"""文件命名与路径处理工具"""
import os
import re
from datetime import datetime


def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'_+', '_', name)  # 合并连续下划线
    name = name.strip().strip('.')
    if not name:
        name = 'video'
    return name


def resolve_filename_conflict(filepath: str) -> str:
    """处理文件名冲突，自动追加序号"""
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    return f"{base}_{counter}{ext}"


def generate_filename(
    template: str,
    title: str = "",
    platform: str = "",
    fmt: str = "mp4",
    video_id: str = "",
) -> str:
    """根据命名模板生成文件名（不含扩展名）"""
    now = datetime.now()
    name = template
    name = name.replace('{title}', sanitize_filename(title or 'video'))
    name = name.replace('{platform}', platform or 'unknown')
    name = name.replace('{format}', fmt)
    name = name.replace('{date}', now.strftime('%Y%m%d'))
    name = name.replace('{time}', now.strftime('%H%M%S'))
    name = name.replace('{id}', sanitize_filename(video_id or ''))
    if not name.strip():
        name = sanitize_filename(title or 'video')
    return name


def get_save_path(base_dir: str, filename: str, extension: str,
                  platform: str = "", sub_by_platform: bool = False,
                  sub_by_date: bool = False) -> str:
    """获取最终保存路径"""
    path = base_dir
    if sub_by_platform and platform:
        from app.utils.link_utils import source_to_folder
        path = os.path.join(path, source_to_folder(platform))
    if sub_by_date:
        path = os.path.join(path, datetime.now().strftime('%Y-%m-%d'))
    os.makedirs(path, exist_ok=True)
    ext = extension.lstrip('.')
    full = os.path.join(path, f"{filename}.{ext}")
    return resolve_filename_conflict(full)
