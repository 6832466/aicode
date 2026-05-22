"""
数据模型定义
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TaskItem:
    """单个转换任务"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    file_path: str = ""                         # 音视频文件路径
    file_name: str = ""                         # 文件名（显示用）
    mode: str = "asr"                           # "asr" 或 "alignment"
    state: str = "pending"                      # 任务状态
    progress: float = 0.0                       # 0.0 ~ 1.0
    progress_text: str = ""                     # 进度文字描述
    script_text: str = ""                       # 强制对齐模式的文稿
    script_source: str = ""                     # 文稿来源: manual/imported_txt/asr_prefill
    srt_path: Optional[str] = None              # 生成的字幕文件路径
    error: Optional[str] = None                 # 错误信息
    audio_extracted_path: Optional[str] = None  # 提取的音频路径
    segments_count: int = 0                     # VAD 分段数
    current_segment: int = 0                    # 当前处理段

    @property
    def is_asr_mode(self) -> bool:
        return self.mode == "asr"

    @property
    def is_alignment_mode(self) -> bool:
        return self.mode == "alignment"

    @property
    def mode_label(self) -> str:
        return "ASR 转写" if self.mode == "asr" else "强制对齐"

    @property
    def state_label(self) -> str:
        labels = {
            "pending": "等待中",
            "extracting": "提取音频",
            "vad": "语音分段",
            "asr": "语音识别",
            "aligning": "文本对齐",
            "punctuate": "标点恢复",
            "writing": "生成字幕",
            "done": "已完成",
            "failed": "失败",
            "stopped": "已停止",
        }
        return labels.get(self.state, self.state)


@dataclass
class SegmentInfo:
    """VAD 语音段信息"""
    start_ms: int
    end_ms: int
    text: str = ""
    confidence: float = 0.0


@dataclass
class SubtitleItem:
    """单条字幕"""
    index: int
    start_ms: int
    end_ms: int
    text: str


@dataclass
class BatchLogEntry:
    """批量处理日志条目"""
    task_id: str
    file_name: str
    mode: str
    state: str
    srt_path: Optional[str] = None
    error: Optional[str] = None
    processed_at: str = ""
    duration_seconds: float = 0.0