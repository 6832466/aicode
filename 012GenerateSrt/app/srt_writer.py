"""
字幕写入器 — SRT 格式生成与后处理
"""

import re
from pathlib import Path
from typing import Optional

from app.models import SegmentInfo, SubtitleItem


def _ms_to_srt_time(ms: int) -> str:
    """毫秒 → SRT 时间格式 HH:MM:SS,mmm"""
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def segments_to_subtitles(
    segments: list[SegmentInfo],
    max_line_chars: int = 20,
    gap_ms: int = 80,
) -> list[SubtitleItem]:
    """
    将 VAD 分段 + ASR/对齐文本转换为字幕条目列表。
    做句子拆分、去重、时间戳平滑。
    """
    items = []
    idx = 1

    for seg in segments:
        if not seg.text or not seg.text.strip():
            continue

        text = seg.text.strip()
        # 按固定长度拆分
        lines = _split_text(text, max_line_chars)

        seg_dur = seg.end_ms - seg.start_ms
        line_dur = seg_dur // len(lines) if lines else seg_dur

        for i, line in enumerate(lines):
            start = seg.start_ms + i * line_dur
            end = seg.start_ms + (i + 1) * line_dur
            if i == len(lines) - 1:
                end = seg.end_ms

            # 时间戳平滑：相邻字幕间留 gap_ms
            if items:
                prev_end = items[-1].end_ms
                if start < prev_end + gap_ms:
                    start = prev_end + gap_ms

            if end <= start:
                continue

            items.append(SubtitleItem(
                index=idx,
                start_ms=start,
                end_ms=end,
                text=line,
            ))
            idx += 1

    return items


def _split_text(text: str, max_chars: int) -> list[str]:
    """按最大字数拆分文本"""
    if len(text) <= max_chars:
        return [text]

    result = []
    # 优先按标点拆分
    parts = re.split(r'(?<=[，,。！？；、])', text)
    current = ""
    for part in parts:
        if len(current) + len(part) <= max_chars:
            current += part
        else:
            if current:
                result.append(current)
            # 如果单个 part 仍然太长，硬切
            while len(part) > max_chars:
                result.append(part[:max_chars])
                part = part[max_chars:]
            current = part
    if current:
        result.append(current)

    return result if result else [text]


def write_srt(
    items: list[SubtitleItem],
    output_path: str,
    encoding: str = "utf-8",
) -> str:
    """写入 SRT 文件，返回文件路径"""
    path = Path(output_path)
    lines = []

    for item in items:
        lines.append(str(item.index))
        lines.append(
            f"{_ms_to_srt_time(item.start_ms)} --> {_ms_to_srt_time(item.end_ms)}"
        )
        lines.append(item.text)
        lines.append("")  # 空行

    content = "\n".join(lines)
    path.write_text(content, encoding=encoding)
    return str(path)


def write_txt(items: list[SubtitleItem], output_path: str) -> str:
    """写入纯文本文件"""
    path = Path(output_path)
    lines = [item.text for item in items]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)