"""
ASR 引擎 — SenseVoice 语音识别 + CTC 强制对齐
(占位实现，后续接入 FunASR / SenseVoice)
"""

import logging
from typing import Optional

from app.models import SegmentInfo

logger = logging.getLogger(__name__)


class AsrEngine:
    """
    SenseVoice ASR 引擎封装。
    后续实现:
      - 模式 A (ASR): funasr.AutoModel → 语音转文字 + 时间戳
      - 模式 B (CTC 对齐): 给定音频 + 文本 → 输出每个 token 的时间戳
    """

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = model_dir
        self._model = None  # 后续加载 SenseVoiceSmall
        logger.info(f"[占位] ASR 引擎初始化, 模型目录: {model_dir}")

    def load_model(self):
        """加载 SenseVoice 模型"""
        logger.info("[占位] 加载 SenseVoice 模型...")

    def transcribe(self, audio_path: str, segments: list[SegmentInfo]) -> list[SegmentInfo]:
        """
        模式 A: ASR 转写。
        对每个 VAD 段进行语音识别，填充 text 和 confidence。
        """
        logger.info(f"[占位] ASR 转写: {audio_path}, {len(segments)} 段")
        for i, seg in enumerate(segments):
            seg.text = f"[第{i+1}段转写内容占位]"
            seg.confidence = 0.95
        return segments

    def force_align(
        self, audio_path: str, segments: list[SegmentInfo], reference_text: str,
    ) -> list[SegmentInfo]:
        """
        模式 B: CTC 强制对齐。
        给定音频和正确文本，输出每段的时间戳。
        """
        logger.info(f"[占位] CTC 强制对齐: {audio_path}, 文本长度: {len(reference_text)}")
        # 占位: 简单按字符平均分配时间
        chars = [c for c in reference_text if c.strip()]
        if not chars or not segments:
            return segments

        # 均匀分配
        total_chars = len(chars)
        total_dur = sum(s.end_ms - s.start_ms for s in segments)
        ms_per_char = total_dur / total_chars if total_chars > 0 else 0

        pos = 0
        result = []
        for seg in segments:
            seg_chars = max(1, int((seg.end_ms - seg.start_ms) / ms_per_char))
            seg_chars = min(seg_chars, total_chars - pos)
            text_slice = "".join(chars[pos : pos + seg_chars])
            seg.text = text_slice
            seg.confidence = 0.99
            result.append(seg)
            pos += seg_chars

        return result