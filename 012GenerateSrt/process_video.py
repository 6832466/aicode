"""
单视频处理脚本 v3 — VAD 分段 → ASR → SRT + TXT
支持 SenseVoiceSmall / Paraformer-large 两种模型
"""

import sys, os, re, subprocess
from pathlib import Path

MODEL_DIR = str(Path(__file__).parent / "models")
TARGET_SR = 16000

# ASR 模型选择
MODEL_SENSEVOICE = "iic/SenseVoiceSmall"
MODEL_PARAFORMER = "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
DEFAULT_ASR_MODEL = MODEL_SENSEVOICE  # 短句场景 SenseVoice 更准


# ═══════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════

def extract_audio(video_path: str) -> str:
    """FFmpeg 提取 16kHz 单声道 WAV"""
    audio_path = video_path + ".extracted.wav"
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", str(TARGET_SR), "-ac", "1",
        audio_path,
    ]
    print(f"[FFmpeg] 提取音频...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg 失败: {r.stderr[:300]}")
    return audio_path


def strip_sensevoice_tags(text: str) -> str:
    """去除 SenseVoice 输出的 <|zh|><|HAPPY|>...<|withitn|> 标签"""
    # 移除所有 <|...|> 标签
    cleaned = re.sub(r'<\s*\|\s*[^|]*\s*\|\s*>', '', text)
    # 移除多余空白
    cleaned = re.sub(r'\s+', '', cleaned)
    return cleaned


def clean_subtitle_text(text: str) -> str:
    """去除字幕中的标点符号，只保留中英文字符和空格"""
    # 移除中文标点 + 英文标点，保留字母/数字/中文/空格
    cleaned = re.sub(
        r'[]，。！？；、：""''（）《》【】…—,.!?;:\'\"()-]',
        '', text,
    )
    return cleaned


def ms_to_srt_time(ms: int) -> str:
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def split_text(text: str, max_chars: int = 20) -> list[str]:
    """按标点（语气停顿）拆分文本为自然短句，合并短句以适配 max_chars"""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # 1. 按标点拆成短句（clauses），保留标点用于判断断句位置
    clauses = re.split(r'(?<=[，,。！？；、\n])', text)
    clauses = [c for c in clauses if c]

    # 2. 合并相邻短句，使每行尽量接近 max_chars
    result, current = [], ""
    for clause in clauses:
        if len(current) + len(clause) <= max_chars:
            current += clause
        else:
            if current:
                result.append(current)
            # 若单个从句本身超过 max_chars，硬切
            while len(clause) > max_chars:
                result.append(clause[:max_chars])
                clause = clause[max_chars:]
            current = clause
    if current:
        result.append(current)

    return result if result else [text]


# ═══════════════════════════════════════════════════════════
#  核心处理
# ═══════════════════════════════════════════════════════════

def run_vad_and_asr(audio_path: str, device: str = "cpu",
                     progress_callback=None,
                     asr_model_name: str = DEFAULT_ASR_MODEL) -> list[dict]:
    """
    分两步:
    1. VAD 获取语音段时间戳
    2. 每段跑 ASR 获取文本
    返回: [{start_ms, end_ms, text}, ...]
    progress_callback(stage, current, total) — stage: "vad"|"asr"
    asr_model_name: MODEL_SENSEVOICE 或 MODEL_PARAFORMER
    """
    from funasr import AutoModel
    import torch

    # 验证 device 可用性
    if device == "cuda" and not torch.cuda.is_available():
        print("[警告] CUDA 不可用，回退到 CPU")
        device = "cpu"
    print(f"[设备] 使用: {device.upper()}")

    # ── 第一步: VAD ──
    print("[VAD] 加载 FSMN-VAD 模型...")
    vad_model = AutoModel(
        model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        model_revision="master",
        model_dir=MODEL_DIR,
        device=device,
        disable_update=True,
    )

    print(f"[VAD] 检测语音段...")
    vad_result = vad_model.generate(input=audio_path)

    # 解析 VAD 结果获取时间戳
    MAX_SEGMENT_MS = 60000  # 单段最长60秒，超出则切分
    segments = []
    if vad_result and len(vad_result) > 0:
        vad_data = vad_result[0]
        if isinstance(vad_data, dict):
            val = vad_data.get("value", [])
            if isinstance(val, list) and len(val) > 0:
                # 格式1: [[start_ms, end_ms], [start_ms, end_ms], ...]
                # 格式2: [{"start": ..., "end": ..., "text": ...}, ...]
                for seg in val:
                    if isinstance(seg, (list, tuple)) and len(seg) >= 2:
                        s, e = int(seg[0]), int(seg[1])
                        if e < 1000 and s < 100 and e > s:
                            s, e = int(s * 1000), int(e * 1000)
                        if e > s:
                            segments.append({"start_ms": s, "end_ms": e, "text": ""})
                    elif isinstance(seg, dict):
                        s = seg.get("start", 0)
                        e = seg.get("end", 0)
                        if e < 1000 and s < 100 and e > s:
                            s, e = int(s * 1000), int(e * 1000)
                        if e > s:
                            segments.append({"start_ms": s, "end_ms": e, "text": ""})

    if not segments:
        # 回退: VAD 未检测到语音 → 按固定间隔切分整个音频
        import soundfile as sf
        info = sf.info(audio_path)
        total_ms = int(info.duration * 1000)
        print(f"[VAD] 未检测到语音段，自动按 {MAX_SEGMENT_MS//1000} 秒间隔切分整个音频 ({total_ms}ms)")
        for chunk_start in range(0, total_ms, MAX_SEGMENT_MS):
            chunk_end = min(chunk_start + MAX_SEGMENT_MS, total_ms)
            if chunk_end - chunk_start > 500:  # 至少0.5秒
                segments.append({"start_ms": chunk_start, "end_ms": chunk_end, "text": ""})

    # 对检测到的段也做长度限制，超长段做进一步切分
    final_segments = []
    for seg in segments:
        dur = seg["end_ms"] - seg["start_ms"]
        if dur <= MAX_SEGMENT_MS:
            final_segments.append(seg)
        else:
            # 切分成多个子段
            n_chunks = (dur + MAX_SEGMENT_MS - 1) // MAX_SEGMENT_MS
            chunk_dur = dur // n_chunks
            for c in range(n_chunks):
                cs = seg["start_ms"] + c * chunk_dur
                ce = seg["end_ms"] if c == n_chunks - 1 else seg["start_ms"] + (c + 1) * chunk_dur
                if ce - cs > 500:
                    final_segments.append({"start_ms": cs, "end_ms": ce, "text": ""})
    segments = final_segments

    print(f"[VAD] 检测到 {len(segments)} 个语音段")
    if progress_callback:
        progress_callback("vad", len(segments), len(segments))

    is_sensevoice = (asr_model_name == MODEL_SENSEVOICE)

    # ── 第二步: ASR 逐段识别 ──
    model_label = "SenseVoiceSmall" if is_sensevoice else "Paraformer-large"
    print(f"[ASR] 加载模型 {model_label}...")
    asr_model = AutoModel(
        model=asr_model_name,
        model_revision="master",
        model_dir=MODEL_DIR,
        device=device,
        disable_update=True,
    )

    total = len(segments)
    import soundfile as sf
    import numpy as np

    # TARGET_SR=16000，音频提取时已统一为此采样率
    sr = TARGET_SR

    for i, seg in enumerate(segments):
        print(f"[ASR] 识别第 {i+1}/{total} 段 ({seg['start_ms']}-{seg['end_ms']}ms)...")
        if progress_callback:
            progress_callback("asr", i + 1, total)

        # 从音频中截取该段
        start_sec = seg["start_ms"] / 1000.0
        end_sec = seg["end_ms"] / 1000.0
        duration = end_sec - start_sec

        if duration < 0.3:
            seg["text"] = ""
            continue

        try:
            # 使用 soundfile 读取音频片段，避免 torchaudio/torchcodec 兼容问题
            audio_data, _ = sf.read(
                audio_path,
                start=int(start_sec * sr),
                frames=int(duration * sr),
                dtype="float32",
            )
            # soundfile 返回 (samples,) 或 (samples, channels)，确保是 2D
            if audio_data.ndim == 1:
                audio_data = audio_data.reshape(-1, 1)
            # 保存为临时段文件
            seg_path = audio_path + f".seg{i}.wav"
            sf.write(seg_path, audio_data, sr)

            if is_sensevoice:
                asr_result = asr_model.generate(
                    input=seg_path,
                    language="zh",
                    use_itn=True,
                    batch_size_s=60,
                )
            else:
                # Paraformer: 不需要 language/use_itn 参数
                asr_result = asr_model.generate(
                    input=seg_path,
                    batch_size_s=60,
                )

            # 提取文本
            if asr_result and len(asr_result) > 0:
                r0 = asr_result[0]
                raw_text = ""
                if isinstance(r0, dict):
                    if "text" in r0:
                        raw_text = r0["text"]
                    else:
                        for k, v in r0.items():
                            if k == "key":
                                continue
                            if isinstance(v, dict) and "text" in v:
                                raw_text = v["text"]
                                break
                            elif isinstance(v, str):
                                raw_text = v
                                break
                            elif isinstance(v, list) and len(v) > 0:
                                if isinstance(v[0], dict) and "text" in v[0]:
                                    raw_text = v[0]["text"]
                                    break
                elif isinstance(r0, str):
                    raw_text = r0

                # SenseVoice 需要去标签，Paraformer 输出已是纯文本
                if is_sensevoice:
                    seg["text"] = strip_sensevoice_tags(raw_text)
                else:
                    seg["text"] = raw_text
            else:
                seg["text"] = ""

            # 清理临时段文件
            if os.path.exists(seg_path):
                os.remove(seg_path)

        except Exception as e:
            print(f"  [警告] 段 {i+1} 识别失败: {e}")
            seg["text"] = ""

    # 过滤空文本段
    segments = [s for s in segments if s["text"] and s["text"].strip()]
    print(f"[结果] 有效字幕段: {len(segments)}")
    return segments


# ═══════════════════════════════════════════════════════════
#  强制对齐 (CTC Forced Alignment)
# ═══════════════════════════════════════════════════════════

MAX_CHUNK_SECONDS = 60  # 每次对齐最长 60 秒，防止 OOM


def run_force_alignment(audio_path: str, script_text: str, device: str = "cpu",
                         progress_callback=None, max_line_chars: int = 12) -> list[dict]:
    """
    CTC 强制对齐: 将参考文本精确对齐到音频时间轴
    先 VAD 分段，再逐段对齐，防止长音频 OOM

    返回: [{start_ms, end_ms, text}, ...] 按标点分句的段
    """
    from funasr import AutoModel

    cleaned = script_text.strip()
    cleaned = re.sub(r'\s+', '', cleaned)
    if not cleaned:
        raise ValueError("参考文本为空")

    # ── 第一步: VAD 分段 ──
    if progress_callback:
        progress_callback("vad", 0, 1)

    print("[对齐] 第一步: VAD 分割语音段...")
    segments_info = _run_vad_for_alignment(audio_path, device)

    if not segments_info:
        # VAD 未检测到语音，按固定时长切分
        import wave
        with wave.open(audio_path, "rb") as wf:
            total_frames = wf.getnframes()
            total_dur_ms = int(total_frames / TARGET_SR * 1000)
        chunk_ms = MAX_CHUNK_SECONDS * 1000
        for t in range(0, total_dur_ms, chunk_ms):
            segments_info.append({
                "start_ms": t,
                "end_ms": min(t + chunk_ms, total_dur_ms),
            })

    total_speech_ms = sum(s["end_ms"] - s["start_ms"] for s in segments_info)

    print(f"[对齐] VAD 检测到 {len(segments_info)} 个语音段, 总时长 {total_speech_ms/1000:.1f}s")

    # ── 第二步: 合并为 ≤MAX_CHUNK_SECONDS 的块 ──
    max_chunk_ms = MAX_CHUNK_SECONDS * 1000
    chunks = []
    current_chunk = {"segments": [], "start_ms": None, "end_ms": None}
    current_dur = 0

    for seg in segments_info:
        dur = seg["end_ms"] - seg["start_ms"] if seg["end_ms"] is not None else max_chunk_ms
        if current_dur + dur > max_chunk_ms and current_chunk["segments"]:
            chunks.append(current_chunk)
            current_chunk = {"segments": [], "start_ms": None, "end_ms": None}
            current_dur = 0
        if current_chunk["start_ms"] is None:
            current_chunk["start_ms"] = seg["start_ms"]
        current_chunk["segments"].append(seg)
        current_chunk["end_ms"] = seg["end_ms"]
        current_dur += dur

    if current_chunk["segments"]:
        chunks.append(current_chunk)

    print(f"[对齐] 合并为 {len(chunks)} 个处理块")

    # ── 第三步: 加载对齐模型（只加载一次）──
    from funasr import AutoModel
    print("[对齐] 加载 MonotonicAligner (fa-zh) 模型...")
    align_model = AutoModel(
        model="fa-zh",
        device=device,
        model_dir=MODEL_DIR,
        disable_update=True,
    )

    # ── 第四步: 按语音时长比例分配文本并逐段对齐 ──
    total_chars = len(cleaned)
    char_pos = 0
    all_segments = []

    if progress_callback:
        progress_callback("aligning", 0, len(chunks))

    for chunk_idx, chunk in enumerate(chunks):
        chunk_dur = chunk["end_ms"] - chunk["start_ms"] if chunk["end_ms"] is not None else max_chunk_ms
        ratio = chunk_dur / total_speech_ms if total_speech_ms > 0 else 1.0
        chunk_chars = max(1, int(total_chars * ratio))
        end_pos = min(char_pos + chunk_chars, total_chars)
        if chunk_idx < len(chunks) - 1:
            for punct in "，,。！？；、\n":
                pos = cleaned.rfind(punct, char_pos, end_pos + 20)
                if pos > char_pos and pos < end_pos + 20:
                    end_pos = pos + 1
                    break
        end_pos = min(end_pos, total_chars)
        chunk_text = cleaned[char_pos:end_pos]

        if not chunk_text:
            char_pos = end_pos
            continue

        chunk_audio_path = _slice_audio(audio_path, chunk["start_ms"], chunk["end_ms"])

        try:
            chunk_segments = _align_one_chunk(
                align_model, chunk_audio_path, chunk_text, chunk["start_ms"],
                max_line_chars,
            )
            all_segments.extend(chunk_segments)
        finally:
            if os.path.exists(chunk_audio_path):
                os.remove(chunk_audio_path)

        char_pos = end_pos

        if progress_callback:
            progress_callback("aligning", chunk_idx + 1, len(chunks))

    if not all_segments:
        raise RuntimeError("强制对齐未产生有效段，请检查文稿是否与音频匹配")

    if progress_callback:
        progress_callback("done", len(all_segments), len(all_segments))

    print(f"[对齐] 完成: {len(all_segments)} 段")
    return all_segments


def _run_vad_for_alignment(audio_path: str, device: str) -> list[dict]:
    """运行 VAD 获取语音段时间戳"""
    from funasr import AutoModel

    vad_model = AutoModel(
        model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        model_revision="master",
        model_dir=MODEL_DIR,
        device=device,
        disable_update=True,
    )
    vad_result = vad_model.generate(input=audio_path)

    segments = []
    if vad_result and len(vad_result) > 0:
        vad_data = vad_result[0]
        if isinstance(vad_data, dict) and "value" in vad_data:
            for item in vad_data["value"]:
                start_ms = int(item[0])
                end_ms = int(item[1])
                if end_ms - start_ms > 300:  # 最小 300ms
                    segments.append({"start_ms": start_ms, "end_ms": end_ms})

    return segments


def _slice_audio(audio_path: str, start_ms: int, end_ms: int) -> str:
    """截取音频片段"""
    import subprocess as sp
    out_path = audio_path + f".chunk_{start_ms}_{end_ms}.wav"
    dur_sec = (end_ms - start_ms) / 1000 if end_ms is not None else None

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_ms / 1000),
        "-i", audio_path,
    ]
    if dur_sec is not None:
        cmd += ["-t", str(dur_sec)]
    cmd += [
        "-vn", "-acodec", "pcm_s16le",
        "-ar", str(TARGET_SR), "-ac", "1",
        out_path,
    ]
    sp.run(cmd, capture_output=True)
    return out_path


def _align_one_chunk(align_model, audio_path: str, text: str,
                     offset_ms: int, max_line_chars: int = 12) -> list[dict]:
    """对单个音频块运行强制对齐，返回绝对时间戳的 segments"""
    spaced_text = " ".join(list(text))
    text_file = audio_path + ".script.txt"
    Path(text_file).write_text(spaced_text, encoding="utf-8")

    try:
        res = align_model.generate(
            input=(audio_path, text_file),
            data_type=("sound", "text"),
        )

        if not res or len(res) == 0:
            return []

        timestamps = res[0].get("timestamp", [])
        if not timestamps:
            return []

        for ts in timestamps:
            ts[0] += offset_ms
            ts[1] += offset_ms

        return _build_aligned_segments(text, timestamps, max_line_chars)

    finally:
        if os.path.exists(text_file):
            os.remove(text_file)


def _build_aligned_segments(text: str, timestamps: list,
                           max_line_chars: int = 12) -> list[dict]:
    """将字符级时间戳按标点分句，再按 max_line_chars 切分为字幕行"""
    # 1. 先按标点切从句
    clauses = re.split(r'(?<=[，,。！？；、\n])', text)
    clauses = [c for c in clauses if c]

    char_idx = 0
    segments = []

    for clause in clauses:
        clause_len = len(clause)
        if char_idx + clause_len > len(timestamps):
            remaining = text[char_idx:]
            if remaining and char_idx < len(timestamps):
                ts_start = timestamps[char_idx][0]
                ts_end = timestamps[-1][1]
                segments.append({
                    "start_ms": ts_start, "end_ms": ts_end, "text": remaining,
                })
            break

        clause_ts = timestamps[char_idx:char_idx + clause_len]
        clause_start = clause_ts[0][0]
        clause_end = clause_ts[-1][1]

        # 2. 从句较短则直接使用；较长则按 max_line_chars 二次切分
        if len(clause) <= max_line_chars:
            if clause_end > clause_start:
                segments.append({
                    "start_ms": clause_start,
                    "end_ms": clause_end,
                    "text": clause,
                })
        else:
            # 用 split_text 逻辑切分，再逐行分配字符时间戳
            sub_lines = split_text(clause, max_line_chars)
            sub_offset = 0
            for sub in sub_lines:
                sub_len = len(sub)
                sub_ts = clause_ts[sub_offset:sub_offset + sub_len]
                if sub_ts:
                    s = sub_ts[0][0]
                    e = sub_ts[-1][1]
                    if e > s:
                        segments.append({
                            "start_ms": s, "end_ms": e, "text": sub,
                        })
                sub_offset += sub_len

        char_idx += clause_len

    return segments


# ═══════════════════════════════════════════════════════════
#  字幕生成
# ═══════════════════════════════════════════════════════════

def generate_srt(segments: list[dict], output_path: str, max_line_chars: int = 15):
    """生成 SRT 文件 — 按时长比例分配时间戳"""
    lines, idx = [], 1
    prev_end_ms = -100  # 上一条字幕结束时间

    for seg in segments:
        raw_text = seg["text"]
        if not raw_text:
            continue

        start_ms = seg["start_ms"]
        end_ms = seg["end_ms"]
        seg_dur = end_ms - start_ms
        if seg_dur <= 0:
            continue

        # 用带标点的原文做切分，切完再去标点
        sub_lines_raw = split_text(raw_text, max_line_chars)
        sub_lines = [clean_subtitle_text(ln) for ln in sub_lines_raw]
        sub_lines = [ln for ln in sub_lines if ln]

        # 单字行合并：向后合并优先，向前合并兜底
        merged = []
        i = 0
        while i < len(sub_lines):
            ln = sub_lines[i]
            if len(ln) == 1 and merged:
                merged[-1] += ln
                i += 1
            elif len(ln) == 1 and i + 1 < len(sub_lines):
                sub_lines[i + 1] = ln + sub_lines[i + 1]
                i += 1
            else:
                merged.append(ln)
                i += 1
        sub_lines = merged
        if not sub_lines:
            continue

        # 计算每行时长（按字符数比例）
        total_chars = sum(len(ln) for ln in sub_lines)
        if total_chars == 0:
            continue

        for j, line in enumerate(sub_lines):
            # 按比例分配，最少 300ms
            this_dur = int(seg_dur * len(line) / total_chars)
            if this_dur < 300:
                this_dur = 300

            # 起始时间：段起点 或 上条结束+80ms 取最大值
            s = max(start_ms, prev_end_ms + 80)
            e = s + this_dur

            # 末行填满剩余时间
            if j == len(sub_lines) - 1:
                e = max(e, end_ms)

            # 不超出段边界
            if e > end_ms:
                e = end_ms

            if e <= s:
                continue

            lines.append(str(idx))
            lines.append(f"{ms_to_srt_time(s)} --> {ms_to_srt_time(e)}")
            lines.append(line)
            lines.append("")
            idx += 1
            prev_end_ms = e

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"[SRT] 已保存: {output_path} ({idx-1} 条字幕)")


def generate_txt(segments: list[dict], output_path: str):
    """生成纯文本"""
    lines = [s["text"] for s in segments if s["text"].strip()]
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"[TXT] 已保存: {output_path}")


# ═══════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("用法: python process_video.py <视频路径> [--gpu] [--sensevoice]")
        sys.exit(1)

    video_path = sys.argv[1]
    use_gpu = "--gpu" in sys.argv
    use_sensevoice = "--sensevoice" in sys.argv
    device = "cuda" if use_gpu else "cpu"
    model = MODEL_SENSEVOICE if use_sensevoice else DEFAULT_ASR_MODEL

    if not os.path.exists(video_path):
        print(f"文件不存在: {video_path}")
        sys.exit(1)

    video_dir = str(Path(video_path).parent)
    video_stem = Path(video_path).stem
    srt_path = os.path.join(video_dir, video_stem + ".srt")
    txt_path = os.path.join(video_dir, video_stem + ".txt")
    audio_path = None

    try:
        import time
        t0 = time.time()

        # 1. 提取音频
        audio_path = extract_audio(video_path)

        # 2. VAD + ASR
        segments = run_vad_and_asr(audio_path, device=device, asr_model_name=model)

        # 3. 生成字幕
        generate_srt(segments, srt_path)
        generate_txt(segments, txt_path)

        elapsed = time.time() - t0
        print(f"\n完成! 总耗时: {elapsed:.0f} 秒")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            # 清理可能残留的段文件
            seg_pattern = Path(video_path).name + ".extracted.wav.seg*.wav"
            for f in Path(video_path).parent.glob(seg_pattern):
                try:
                    f.unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    main()