"""日志工具"""

import logging
import sys


def setup_logging(level=logging.DEBUG):
    """初始化日志配置"""
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    root.handlers.clear()
    root.addHandler(handler)

    # 抑制第三方库噪音
    for lib in ("asyncio", "aiohttp", "urllib3", "PIL"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger"""
    return logging.getLogger(name)
