"""
全局常量、路径工具、配置键
"""

import sys
from pathlib import Path


def app_root() -> Path:
    """获取应用根目录 (frozen 时指向 exe 所在目录)"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def app_icon_path() -> Path:
    """获取 1.ico 路径，兼顾 frozen 和开发环境"""
    base = app_root()
    candidates = [
        base / "1.ico",
        base / "_internal" / "1.ico",
        Path(__file__).parent.parent / "1.ico",
        Path(__file__).parent.parent.parent / "1.ico",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def data_dir() -> Path:
    """数据存储目录"""
    d = app_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    """模型存放目录"""
    d = app_root() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 窗口配置 ──
WINDOW_TITLE = "乐乐音视频转字幕工具    微信：rpalele"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 820

# ── 处理配置 ──
DEFAULT_AUDIO_SR = 16000           # 采样率
DEFAULT_AUDIO_CHANNELS = 1         # 单声道
MAX_SEGMENT_SECONDS = 30           # 单段最大秒数
SEGMENT_OVERLAP_SECONDS = 1.5      # 段间重叠秒数
MIN_SPEECH_SECONDS = 0.5           # 最短有效语音段
MAX_LINE_CHARS = 12                # 字幕每行最大字数
SRT_GAP_MS = 80                    # 字幕间距 (ms)

# ── 模式枚举 ──
MODE_ASR = "asr"
MODE_ALIGNMENT = "alignment"

# ── 任务状态枚举 ──
STATE_PENDING = "pending"
STATE_EXTRACTING = "extracting"
STATE_VAD = "vad"
STATE_ASR = "asr"
STATE_ALIGNING = "aligning"
STATE_PUNCTUATE = "punctuate"
STATE_WRITING = "writing"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_STOPPED = "stopped"