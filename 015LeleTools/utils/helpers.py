"""
通用辅助函数
"""

import re
from pathlib import Path
from typing import Optional


def truncate_filename(name: str, max_len: int = 100) -> str:
    """截断文件名到安全长度（保留扩展名）"""
    if len(name) <= max_len:
        return name
    stem = Path(name).stem[:max_len - 10]
    suffix = Path(name).suffix
    return stem + "..." + suffix


def extract_names_from_text(text: str) -> list[str]:
    """从文本中提取可能的人名（简单模式）"""
    # 匹配"XX说"、"XX："、 "XX道" 等模式
    pattern = r'([一-鿿]{2,4})(?:说|道|：|:)'
    matches = re.findall(pattern, text)
    seen = set()
    result = []
    for name in matches:
        if name not in seen and not name.endswith(('自己', '我们', '他们', '你们')):
            seen.add(name)
            result.append(name)
    return result


def format_duration(seconds: float) -> str:
    """格式化时长"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}分{s}秒"
    else:
        h, remainder = divmod(int(seconds), 3600)
        m, s = divmod(remainder, 60)
        return f"{h}时{m}分{s}秒"
