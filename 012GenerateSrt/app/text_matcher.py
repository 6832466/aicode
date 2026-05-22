"""
文本匹配器 — difflib + RapidFuzz 两阶段策略
"""

import re
import difflib
from typing import Optional

# RapidFuzz 为可选依赖，首次匹配尝试使用，失败则回退到 difflib
try:
    from rapidfuzz import fuzz, process
    _has_rapidfuzz = True
except ImportError:
    _has_rapidfuzz = False


def clean_text(text: str) -> str:
    """清洗文本：去标点、转小写（英文）"""
    text = re.sub(r'[^\u4e00-\u9fff\w\s]', '', text)
    text = re.sub(r'\s+', '', text)
    return text.lower()


def fuzzy_locate(asr_text: str, reference: str) -> Optional[tuple[int, int]]:
    """
    在 reference 中查找 asr_text 的最佳匹配位置。
    返回 (start_char_index, end_char_index)，找不到返回 None。

    策略：
    1. 先清洗两段文本（去标点）
    2. RapidFuzz 粗定位（如果可用）
    3. difflib.SequenceMatcher 精确对齐
    """
    asr_clean = clean_text(asr_text)
    ref_clean = clean_text(reference)

    if not asr_clean or not ref_clean:
        return None

    # ── 第一层：RapidFuzz 粗定位 ──
    if _has_rapidfuzz:
        try:
            best_score = 0
            best_start = 0
            best_end = 0
            window = len(asr_clean)
            step = max(1, window // 2)

            for i in range(0, len(ref_clean) - window + 1, step):
                chunk = ref_clean[i : i + window]
                score = fuzz.ratio(asr_clean, chunk)
                if score > best_score:
                    best_score = score
                    best_start = i
                    best_end = i + window

            if best_score < 40:
                return None

            # 缩小搜索范围
            margin = window // 2
            search_start = max(0, best_start - margin)
            search_end = min(len(ref_clean), best_end + margin)
            ref_search = ref_clean[search_start:search_end]
        except Exception:
            ref_search = ref_clean
            search_start = 0
    else:
        ref_search = ref_clean
        search_start = 0

    # ── 第二层：difflib 精确对齐 ──
    matcher = difflib.SequenceMatcher(None, ref_search, asr_clean)
    blocks = matcher.get_matching_blocks()
    if not blocks:
        return None

    # 取第一个有效匹配块
    for block in blocks:
        if block.size < 3:  # 太短忽略
            continue
        start = search_start + block.a
        end = start + block.size
        return (start, end)

    return None


def match_confidence(asr_text: str, reference: str) -> float:
    """计算两段文本的匹配置信度 (0~1)"""
    if not asr_text or not reference:
        return 0.0

    a = clean_text(asr_text)
    b = clean_text(reference)

    if _has_rapidfuzz:
        try:
            return fuzz.ratio(a, b) / 100.0
        except Exception:
            pass

    return difflib.SequenceMatcher(None, a, b).ratio()


def split_sentences(text: str, max_len: int = 30) -> list[str]:
    """将长文本按标点和长度拆分为句子"""
    if not text:
        return []

    # 按常见标点拆分
    raw = re.split(r'[。！？；\n]', text)
    result = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        # 按逗号半句拆分（更细粒度）
        sub = re.split(r'[，,、]', s)
        current = ""
        for seg in sub:
            seg = seg.strip()
            if not seg:
                continue
            if len(current) + len(seg) <= max_len:
                current += seg
            else:
                if current:
                    result.append(current)
                current = seg
        if current:
            result.append(current)

    return result if result else [text]