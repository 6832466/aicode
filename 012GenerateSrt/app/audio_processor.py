"""
音频处理器 — FFmpeg 提取 + VAD 分段
(占位实现，后续接入真实 FFmpeg + FunASR VAD)
"""

import logging
from pathlib import Path
from typing import Optional

from app.models import SegmentInfo

logger = logging.getLogger(__name__)


class AudioProcessor:
    """音频提取和预处理"""

    def __init__(self, ffmpeg_path: Optional[str] = None, target_sr: int = 16000):
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"
        self.target_sr = target_sr

    def extract_audio(self, video_path: str, output_dir: Optional[Path] = None) -> str:
        """
        从视频提取音频为 16kHz 单声道 WAV。
        后续实现时调用 subprocess.run([ffmpeg, "-i", video_path, ...])。
        """
        base = Path(video_path).stem
        out_dir = output_dir or Path(video_path).parent
        out_path = out_dir / f"{base}_audio.wav"

        # 占位: 假设音频已存在
        logger.info(f"[占位] 提取音频: {video_path} → {out_path}")
        return str(out_path)

    def vad_segment(self, audio_path: str) -> list[SegmentInfo]:
        """
        VAD 语音活动检测。
        后续实现时接入 FunASR FSMN-VAD 模型。
        返回有声片段的起止时间列表。
        """
        # 占位: 模拟分段
        logger.info(f"[占位] VAD 分段: {audio_path}")
        return [
            SegmentInfo(start_ms=0, end_ms=28500),
            SegmentInfo(start_ms=45100, end_ms=85600),
            SegmentInfo(start_ms=92000, end_ms=102000),
        ]

    def split_long_segments(
        self, segments: list[SegmentInfo], max_sec: float = 30.0, overlap_sec: float = 1.5,
    ) -> list[SegmentInfo]:
        """
        将超过 max_sec 的长段拆分成子段，段间留 overlap。
        """
        max_ms = int(max_sec * 1000)
        overlap_ms = int(overlap_sec * 1000)
        result = []

        for seg in segments:
            dur = seg.end_ms - seg.start_ms
            if dur <= max_ms:
                result.append(seg)
                continue

            pos = seg.start_ms
            while pos < seg.end_ms:
                end = min(pos + max_ms, seg.end_ms)
                result.append(SegmentInfo(start_ms=pos, end_ms=end))
                pos = end - overlap_ms  # 下一段从 overlap 处开始

        return result