"""
备份管理器 — 创建、恢复、列出草稿备份。
"""
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


# 备份存储目录（在 AiCode 项目下）
BACKUP_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")


def _ensure_backup_dir() -> str:
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    return BACKUP_ROOT


def create_backup(draft_folder: str) -> str | None:
    """
    将草稿文件夹打包为 zip 备份。
    返回备份文件路径，失败返回 None。
    """
    draft_path = Path(draft_folder)
    if not draft_path.is_dir():
        return None

    _ensure_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{draft_path.name}_{timestamp}.zip"
    backup_path = os.path.join(BACKUP_ROOT, backup_name)

    try:
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(draft_folder):
                for f in files:
                    file_path = os.path.join(root, f)
                    arcname = os.path.relpath(file_path, draft_folder)
                    zf.write(file_path, arcname)
        return backup_path
    except (IOError, PermissionError) as e:
        print(f"备份失败: {e}")
        return None


def restore_backup(backup_path: str, target_folder: str) -> bool:
    """
    从 zip 备份恢复到指定文件夹。
    目标文件夹将被清空后恢复。
    """
    if not os.path.isfile(backup_path):
        return False

    target_path = Path(target_folder)

    try:
        # 清空目标文件夹
        if target_path.is_dir():
            shutil.rmtree(target_path)
        target_path.mkdir(parents=True, exist_ok=True)

        # 解压
        with zipfile.ZipFile(backup_path, "r") as zf:
            zf.extractall(target_path)
        return True
    except (IOError, PermissionError, zipfile.BadZipFile) as e:
        print(f"恢复失败: {e}")
        return False


def list_backups(draft_folder_name: str = None) -> list[dict]:
    """列出备份。可按草稿名过滤。"""
    _ensure_backup_dir()
    backups = []
    try:
        for f in os.listdir(BACKUP_ROOT):
            if not f.endswith(".zip"):
                continue
            full_path = os.path.join(BACKUP_ROOT, f)
            stat = os.stat(full_path)

            # 从文件名解析：草稿名_时间戳.zip
            name_part = f.rsplit("_", 2)  # name_YYYYMMDD_HHMMSS.zip
            draft_name = name_part[0] if len(name_part) >= 2 else f

            if draft_folder_name and draft_folder_name not in f:
                continue

            backups.append({
                "path": full_path,
                "filename": f,
                "draft_name": draft_name,
                "size": stat.st_size,
                "time": stat.st_mtime,
                "time_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
    except (PermissionError, FileNotFoundError):
        pass

    backups.sort(key=lambda b: b["time"], reverse=True)
    return backups


def delete_backup(backup_path: str) -> bool:
    """删除指定备份文件"""
    try:
        if os.path.isfile(backup_path) and backup_path.startswith(BACKUP_ROOT):
            os.remove(backup_path)
            return True
    except (IOError, PermissionError):
        pass
    return False


def open_backup_folder() -> str:
    """返回备份目录路径"""
    return _ensure_backup_dir()
