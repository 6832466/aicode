"""数据模型 - 按需求文档定义"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    """任务状态枚举（按需求文档）"""
    PENDING = "pending"        # 待生成
    GENERATING = "generating"  # 生成中
    COMPLETED = "completed"    # 已完成（视频已生成，等待下载）
    FAILED = "failed"          # 失败
    DOWNLOADING = "downloading"# 下载中
    DOWNLOADED = "downloaded"  # 已下载

    def display(self) -> str:
        """中文显示"""
        return {
            "pending": "待生成",
            "generating": "生成中",
            "completed": "已完成",
            "failed": "失败",
            "downloading": "下载中",
            "downloaded": "已下载",
        }[self.value]

    def color(self) -> str:
        """状态颜色"""
        return {
            "pending": "#94a3b8",      # 灰色
            "generating": "#60a5fa",   # 蓝色
            "completed": "#10b981",    # 绿色
            "failed": "#ef4444",       # 红色
            "downloading": "#60a5fa",  # 蓝色
            "downloaded": "#10b981",   # 绿色
        }[self.value]


class DownloadStatus(str, Enum):
    """下载状态枚举"""
    PENDING = "pending"          # 待下载
    DOWNLOADING = "downloading"  # 下载中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    PAUSED = "paused"            # 已暂停

    def display(self) -> str:
        return {
            "pending": "待下载",
            "downloading": "下载中",
            "completed": "已完成",
            "failed": "失败",
            "paused": "已暂停",
        }[self.value]


class MaterialType(str, Enum):
    """素材类型枚举"""
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"

    def display(self) -> str:
        return {"image": "图片", "audio": "音频", "video": "视频"}[self.value]

    def icon(self) -> str:
        return {"image": "🖼", "audio": "🎵", "video": "🎬"}[self.value]


@dataclass
class MaterialInfo:
    """素材信息"""
    character_name: str       # 关联人物名
    file_path: str            # 本地文件路径
    material_type: MaterialType
    file_size: int = 0        # 文件大小（字节）
    file_extension: str = ""  # 文件扩展名
    exists: bool = True       # 文件是否存在
    column_name: str = ""     # Excel列名（用于追溯）

    def to_dict(self) -> dict:
        d = asdict(self)
        d["material_type"] = self.material_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> MaterialInfo:
        d["material_type"] = MaterialType(d["material_type"])
        return cls(**d)


@dataclass
class GenerationRecord:
    """生成历史记录"""
    generated_at: str           # ISO format timestamp
    jm_task_id: str             # 即梦返回的任务ID（submit_id）
    status: str = "submitted"   # submitted/completed/failed
    video_url: Optional[str] = None
    error_msg: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> GenerationRecord:
        return cls(**d)


@dataclass
class Task:
    """生成任务（按需求文档定义）"""
    # 必填字段（从Excel读取）
    seq: int                    # 序号（从1开始）
    scene: str                  # 场次（如"第1场"）
    prompt: str                 # 完整提示词
    duration: int = 12          # 时长（秒，范围5~15）
    ratio: str = "16:9"         # 比例（16:9/9:16/1:1/4:3）

    # 系统字段
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: TaskStatus = TaskStatus.PENDING

    # 即梦API返回
    jm_task_id: Optional[str] = None  # submit_id
    video_url: Optional[str] = None   # 视频下载链接

    # 关联数据
    materials: list[MaterialInfo] = field(default_factory=list)
    history: list[GenerationRecord] = field(default_factory=list)

    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 错误信息
    error_msg: Optional[str] = None

    # 分辨率
    resolution: str = "720p"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["materials"] = [m.to_dict() for m in self.materials]
        d["history"] = [h.to_dict() for h in self.history]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Task:
        d["status"] = TaskStatus(d["status"])
        d["materials"] = [MaterialInfo.from_dict(m) for m in d.get("materials", [])]
        d["history"] = [GenerationRecord.from_dict(h) for h in d.get("history", [])]
        return cls(**d)

    def update_timestamp(self):
        """更新时间戳"""
        self.updated_at = datetime.now().isoformat()

    def add_history(self, record: GenerationRecord):
        """添加生成历史"""
        self.history.append(record)
        self.update_timestamp()


@dataclass
class DownloadTask:
    """下载任务"""
    url: str                    # 视频URL
    scene: str                  # 关联场次
    seq: int                    # 关联序号
    filename: str               # 保存文件名

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_id: Optional[str] = None  # 关联的Task.id
    file_size: int = 0          # 总字节
    downloaded_bytes: int = 0   # 已下载字节
    progress: float = 0.0       # 0.0 ~ 1.0
    status: DownloadStatus = DownloadStatus.PENDING
    save_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    error_msg: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> DownloadTask:
        d["status"] = DownloadStatus(d["status"])
        return cls(**d)


@dataclass
class CharacterMaterial:
    """人物素材（用于素材管理页）"""
    character_name: str         # 人物名
    materials: list[MaterialInfo] = field(default_factory=list)  # 该人物的所有素材

    def to_dict(self) -> dict:
        d = asdict(self)
        d["materials"] = [m.to_dict() for m in self.materials]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> CharacterMaterial:
        d["materials"] = [MaterialInfo.from_dict(m) for m in d.get("materials", [])]
        return cls(**d)