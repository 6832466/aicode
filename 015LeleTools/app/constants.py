"""
全局常量、路径工具
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
        base.parent / "1.ico",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def config_path() -> Path:
    """配置文件路径"""
    return app_root() / "config.json"


def data_dir() -> Path:
    """数据存储目录"""
    d = app_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def chat_history_dir() -> Path:
    """对话历史目录"""
    d = data_dir() / "chats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def rewrite_history_dir() -> Path:
    """改文记录目录"""
    d = data_dir() / "rewrites"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 窗口配置 ──
WINDOW_TITLE = "乐乐智能工具箱    微信：rpalele"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 820

# ── 默认值 ──
DEFAULT_SEGMENT_SIZE = 4000
DEFAULT_TIMEOUT = 60
DEFAULT_MODEL = "gemini-2.5-pro"
DEFAULT_MAX_CONTEXT = 20

# ── API 重试配置 ──
MAX_RETRIES = 3
RETRY_DELAY = 2
RETRY_STATUSES = {429, 502, 503, 504}

# ── 改文指令 ──
INSTRUCTION_FIX_TYPOS = "改错别字"
INSTRUCTION_EXTRACT_NAMES = "提取人名"
INSTRUCTION_SPLIT_SCENES = "分镜/文案分解"
INSTRUCTION_LONG_SIMPLIFY = "长篇精简"
INSTRUCTION_SCENE_REWRITE = "分镜洗稿"
INSTRUCTION_CHANGE_PERSON = "单改人称"
INSTRUCTION_GENDER_SWAP = "性别转换"

ALL_INSTRUCTIONS = [
    INSTRUCTION_FIX_TYPOS,
    INSTRUCTION_EXTRACT_NAMES,
    INSTRUCTION_SPLIT_SCENES,
    INSTRUCTION_LONG_SIMPLIFY,
    INSTRUCTION_SCENE_REWRITE,
    INSTRUCTION_CHANGE_PERSON,
    INSTRUCTION_GENDER_SWAP,
]
