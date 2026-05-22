"""
音频后处理配置 & 处理引擎
依赖: PyQt5 + PyQt-Fluent-Widgets + numpy + scipy + soundfile + ffmpeg
"""

import os, sys, tempfile, subprocess, traceback, datetime, io
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# 修复 Windows GBK 编码问题：强制 stdout/stderr 使用 UTF-8
if sys.platform == 'win32':
    if sys.stdout is not None and hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr is not None and hasattr(sys.stderr, 'buffer') and sys.stderr.buffer is not None:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── 调试日志 ──────────────────────────────────────────
_LOG_PATH = os.path.join(tempfile.gettempdir(), "audio_tool_debug.log")
def _log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
_log(f"=== 程序启动 pid={os.getpid()} ===")

# 全局异常捕获
def _global_excepthook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _log(f"未捕获异常:\n{msg}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)
sys.excepthook = _global_excepthook

# C 级别崩溃 (segfault) 追踪
try:
    import faulthandler
    _fh = open(_LOG_PATH, "a")
    faulthandler.enable(file=_fh, all_threads=True)
except Exception:
    pass

import numpy as np
from scipy import signal as sig
from scipy.ndimage import uniform_filter1d

from PyQt5.QtCore import Qt, pyqtSignal, QThread, QEvent
from PyQt5.QtGui import QFont, QDragEnterEvent, QDropEvent, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QWidget, QFrame, QScrollArea, QFileDialog,
    QListWidget, QListWidgetItem, QAbstractItemView, QMessageBox,
)

from qfluentwidgets import (
    CheckBox, Slider, PrimaryPushButton, TransparentPushButton,
    BodyLabel, StrongBodyLabel, SubtitleLabel, CaptionLabel,
    ProgressBar, IndeterminateProgressBar,
    setTheme, Theme, setThemeColor, isDarkTheme, themeColor,
    FluentStyleSheet,
)

# ═══════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════

AUDIO_EXTENSIONS  = {".wav", ".mp3", ".flac", ".aac", ".ogg", ".wma", ".m4a",
                     ".aiff", ".ape", ".opus", ".alac", ".ac3", ".amr"}
VIDEO_EXTENSIONS  = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm",
                     ".mts", ".m2ts", ".ts", ".3gp", ".rmvb", ".vob"}
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
OUTPUT_SUFFIX = "_lele"

def _ffmpeg_path() -> str:
    """定位 ffmpeg.exe，优先同目录下的 ffmpeg 文件夹。"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(base, "ffmpeg", "ffmpeg.exe")
    if os.path.isfile(bundled):
        return bundled
    return "ffmpeg"  # fallback: 依赖系统 PATH

# ═══════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════

@dataclass
class SilenceShortenConfig:
    enabled: bool = False
    target_duration_ms: int = 120
    threshold_db: int = -30

@dataclass
class HardLimiterConfig:
    enabled: bool = True
    max_level_db: float = -1.0
    input_gain_db: float = 6.0

@dataclass
class EqualizerConfig:
    enabled: bool = True
    preset_index: int = 0  # 柔和高音提升

@dataclass
class DeEsserConfig:
    enabled: bool = False
    threshold_db: float = -30.0       # 齿音检测阈值
    reduction_db: float = 6.0         # 最大衰减量（适度去齿音）
    makeup_gain_db: float = 2.0       # 补偿增益（去齿音会略微压低整体音量）

@dataclass
class CompressorConfig:
    enabled: bool = True
    threshold_db: float = -10.0       # 压缩阈值
    ratio: float = 3.0               # 压缩比
    attack_ms: float = 15.0          # 起控时间
    release_ms: float = 200.0        # 释放时间
    makeup_gain_db: float = 0.0      # 补偿增益

@dataclass
class NoiseReductionConfig:
    enabled: bool = False
    reduction_db: float = 12.0        # 降噪强度 (6-20dB)
    threshold_db: float = -50.0       # 噪声判定阈值

@dataclass
class AudioConfig:
    silence_shorten: SilenceShortenConfig = field(default_factory=SilenceShortenConfig)
    hard_limiter: HardLimiterConfig     = field(default_factory=HardLimiterConfig)
    compressor: CompressorConfig        = field(default_factory=CompressorConfig)
    equalizer: EqualizerConfig          = field(default_factory=EqualizerConfig)
    de_esser: DeEsserConfig            = field(default_factory=DeEsserConfig)
    noise_reduction: NoiseReductionConfig = field(default_factory=NoiseReductionConfig)


# ═══════════════════════════════════════════════════════════
# EQ Preset Metadata (UI display)
# ═══════════════════════════════════════════════════════════

EQ_PRESETS = [
    ("柔和高音提升", "低切80Hz + 3.5kHz清晰度 + 10kHz空气感"),
    ("人声提亮",   "增强中高频，更清晰通透"),
    ("人声温暖",   "增强低中频，更饱满温暖"),
    ("人声清晰",   "专注语音清晰度"),
    ("去浑浊",     "衰减中低频，解决发闷"),
    ("去刺耳",     "衰减中高频刺耳部分"),
    ("去齿音",     "衰减齿音频段"),
    ("高切滤波",   "去除高频噪声"),
    ("低切滤波",   "去除低频噪声"),
    ("增加空气感", "提升超高频，更通透"),
    ("低音增强",   "增强低频力量感"),
    ("电话音效",   "模拟电话窄带音"),
    ("广播音效",   "模拟AM广播复古音"),
]


# ═══════════════════════════════════════════════════════════
# Bi-Quad Filter Design —— RBJ Audio Cookbook
# ═══════════════════════════════════════════════════════════

def _bq_peaking(fs: float, f0: float, Q: float, gain_db: float) -> np.ndarray:
    """Peaking EQ → SOS row [b0,b1,b2,a0,a1,a2], a0 未归一化。"""
    A  = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2.0 * Q)
    cos_w = np.cos(w0)
    b = np.array([1.0 + alpha * A, -2.0 * cos_w, 1.0 - alpha * A])
    a = np.array([1.0 + alpha / A, -2.0 * cos_w, 1.0 - alpha / A])
    return np.concatenate([b, a])

def _bq_lowshelf(fs: float, f0: float, Q: float, gain_db: float) -> np.ndarray:
    A  = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2.0 * Q)
    cos_w = np.cos(w0)
    sA = np.sqrt(A) * alpha
    b = A * np.array([
        (A + 1.0) - (A - 1.0) * cos_w + 2.0 * sA,
         2.0 * ((A - 1.0) - (A + 1.0) * cos_w),
        (A + 1.0) - (A - 1.0) * cos_w - 2.0 * sA,
    ])
    a = np.array([
        (A + 1.0) + (A - 1.0) * cos_w + 2.0 * sA,
        -2.0 * ((A - 1.0) + (A + 1.0) * cos_w),
        (A + 1.0) + (A - 1.0) * cos_w - 2.0 * sA,
    ])
    return np.concatenate([b, a])

def _bq_highshelf(fs: float, f0: float, Q: float, gain_db: float) -> np.ndarray:
    A  = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2.0 * Q)
    cos_w = np.cos(w0)
    sA = np.sqrt(A) * alpha
    b = A * np.array([
        (A + 1.0) + (A - 1.0) * cos_w + 2.0 * sA,
       -2.0 * ((A - 1.0) + (A + 1.0) * cos_w),
        (A + 1.0) + (A - 1.0) * cos_w - 2.0 * sA,
    ])
    a = np.array([
        (A + 1.0) - (A - 1.0) * cos_w + 2.0 * sA,
         2.0 * ((A - 1.0) - (A + 1.0) * cos_w),
        (A + 1.0) - (A - 1.0) * cos_w - 2.0 * sA,
    ])
    return np.concatenate([b, a])

def _bq_highpass(fs: float, f0: float, Q: float) -> np.ndarray:
    w0 = 2.0 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2.0 * Q)
    cos_w = np.cos(w0)
    b = np.array([(1.0 + cos_w) / 2.0, -(1.0 + cos_w), (1.0 + cos_w) / 2.0])
    a = np.array([1.0 + alpha, -2.0 * cos_w, 1.0 - alpha])
    return np.concatenate([b, a])

def _bq_lowpass(fs: float, f0: float, Q: float) -> np.ndarray:
    w0 = 2.0 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2.0 * Q)
    cos_w = np.cos(w0)
    b = np.array([(1.0 - cos_w) / 2.0, 1.0 - cos_w, (1.0 - cos_w) / 2.0])
    a = np.array([1.0 + alpha, -2.0 * cos_w, 1.0 - alpha])
    return np.concatenate([b, a])

def _to_sos(biquads: np.ndarray) -> np.ndarray:
    """将多行 [b0,b1,b2,a0,a1,a2] 归一化为 scipy SOS 格式。"""
    sos = biquads.copy().reshape(-1, 6)
    a0 = sos[:, 3:4].copy()
    sos /= a0                       # b 和 a 同时除以 a0
    return sos


# ═══════════════════════════════════════════════════════════
# EQ Preset → SOS Filter Chains
# ═══════════════════════════════════════════════════════════

def build_eq_sos(preset_index: int, fs: float) -> np.ndarray:
    """根据 preset_index 返回级联 SOS 矩阵。"""
    bqs = []

    if preset_index == 0:          # 柔和高音提升
        bqs.append(_bq_highpass(fs, 80, 0.7))          # 低切去噪
        bqs.append(_bq_peaking(fs, 3500, 1.0, 2.0))    # 3.5kHz 微增清晰度
        bqs.append(_bq_highshelf(fs, 10000, 0.7, 2.5)) # 10kHz 以上柔和空气感

    elif preset_index == 1:        # 人声提亮
        bqs.append(_bq_peaking(fs, 3000, 0.8, 3.0))
        bqs.append(_bq_highshelf(fs, 8000, 0.7, 4.0))

    elif preset_index == 2:        # 人声温暖
        bqs.append(_bq_lowshelf(fs, 200, 0.7, 3.0))
        bqs.append(_bq_peaking(fs, 400, 1.2, 2.5))

    elif preset_index == 3:        # 人声清晰
        bqs.append(_bq_highpass(fs, 80, 0.7))
        bqs.append(_bq_peaking(fs, 2500, 0.7, 4.0))
        bqs.append(_bq_peaking(fs, 6000, 1.0, 2.0))

    elif preset_index == 4:        # 去浑浊
        bqs.append(_bq_peaking(fs, 300, 1.5, -5.0))
        bqs.append(_bq_peaking(fs, 500, 1.5, -3.0))

    elif preset_index == 5:        # 去刺耳
        bqs.append(_bq_peaking(fs, 4000, 1.5, -4.0))
        bqs.append(_bq_peaking(fs, 6000, 1.5, -3.0))

    elif preset_index == 6:        # 去齿音
        bqs.append(_bq_peaking(fs, 7000, 1.5, -6.0))

    elif preset_index == 7:        # 高切滤波
        bqs.append(_bq_lowpass(fs, 8000, 0.7))

    elif preset_index == 8:        # 低切滤波
        bqs.append(_bq_highpass(fs, 80, 0.7))

    elif preset_index == 9:        # 增加空气感
        bqs.append(_bq_highshelf(fs, 10000, 0.7, 5.0))

    elif preset_index == 10:       # 低音增强
        bqs.append(_bq_lowshelf(fs, 100, 0.7, 6.0))

    elif preset_index == 11:       # 电话音效
        bqs.append(_bq_highpass(fs, 300, 0.7))
        bqs.append(_bq_lowpass(fs, 3400, 0.7))

    elif preset_index == 12:       # 广播音效
        bqs.append(_bq_highpass(fs, 200, 0.7))
        bqs.append(_bq_lowpass(fs, 5000, 0.7))

    if not bqs:
        return np.empty((0, 6))
    return _to_sos(np.vstack(bqs))


# ═══════════════════════════════════════════════════════════
# Audio Processor
# ═══════════════════════════════════════════════════════════

class AudioProcessor(QThread):
    """后台音频处理线程 —— 避免阻塞 UI。"""
    progress  = pyqtSignal(int, int)       # (current, total)
    stepChanged = pyqtSignal(str)          # 当前步骤描述
    finished  = pyqtSignal()
    log       = pyqtSignal(str)

    def __init__(self, file_pairs: List[Tuple[str, str]], config: AudioConfig, parent=None):
        super().__init__(parent)
        self._pairs  = file_pairs
        self._config = config

    def run(self):
        _log("AudioProcessor.run 开始")
        total = len(self._pairs)
        for idx, (inp, out) in enumerate(self._pairs):
            fname = os.path.basename(inp)
            self.log.emit(f"[{idx+1}/{total}] {fname}")
            self.progress.emit(idx + 1, total)
            self.stepChanged.emit(f"正在处理 ({idx+1}/{total}): {fname}")
            try:
                self._process_one(inp, out)
            except Exception as e:
                _log(f"处理异常: {e}\n{traceback.format_exc()}")
                self.log.emit(f"  ! 错误: {e}")
        _log("AudioProcessor.run 完成，发送 finished 信号")
        self.stepChanged.emit("处理完成")
        self.finished.emit()

    # ── 单文件处理 pipeline ──────────────────────────────

    def _process_one(self, input_path: str, output_path: str):
        _log(f"_process_one 开始: {os.path.basename(input_path)}")
        data, sr = self._read(input_path)
        _log(f"  读取完成: sr={sr}, shape={data.shape}, dtype={data.dtype}")
        original_dtype = data.dtype if not np.issubdtype(data.dtype, np.floating) else np.float32

        # 保持 float32 处理，最小化内存
        if not np.issubdtype(data.dtype, np.floating):
            data = data.astype(np.float32) / np.iinfo(data.dtype).max

        # ---- Pipeline (按顺序) ----
        cfg = self._config

        if cfg.silence_shorten.enabled:
            self.log.emit(f"    → 缩短静音 …")
            self.stepChanged.emit(f"缩短静音 ({cfg.silence_shorten.target_duration_ms}ms / {cfg.silence_shorten.threshold_db}dB)")
            _log("  → 缩短静音")
            data = self._shorten_silence(data, sr, cfg.silence_shorten)
            _log(f"  ← 缩短静音完成, shape={data.shape}")

        if cfg.noise_reduction.enabled:
            self.log.emit(f"    → 降噪 …")
            self.stepChanged.emit(f"降噪 ({cfg.noise_reduction.reduction_db:.0f}dB)")
            _log("  → 降噪")
            data = self._noise_reduction(data, sr, cfg.noise_reduction)
            _log(f"  ← 降噪完成, shape={data.shape}")

        if cfg.hard_limiter.enabled:
            self.log.emit(f"    → 强制限幅 …")
            self.stepChanged.emit(f"强制限幅 (最大 {cfg.hard_limiter.max_level_db}dB / 增益 {cfg.hard_limiter.input_gain_db:+.1f}dB)")
            _log("  → 强制限幅")
            data = self._hard_limit(data, cfg.hard_limiter)
            _log(f"  ← 强制限幅完成, shape={data.shape}")

        if cfg.equalizer.enabled:
            name = EQ_PRESETS[cfg.equalizer.preset_index][0]
            self.log.emit(f"    → 均衡器 [{name}] …")
            self.stepChanged.emit(f"均衡器 [{name}]")
            _log(f"  → 均衡器 [{name}]")
            data = self._apply_eq(data, sr, cfg.equalizer.preset_index)
            _log(f"  ← 均衡器完成, shape={data.shape}")

        if cfg.compressor.enabled:
            self.log.emit(f"    → 动态压缩 …")
            self.stepChanged.emit(f"动态压缩 (阈值 {cfg.compressor.threshold_db}dB / {cfg.compressor.ratio:.0f}:1)")
            _log("  → 动态压缩")
            data = self._compressor(data, sr, cfg.compressor)
            _log(f"  ← 动态压缩完成, shape={data.shape}")

        if cfg.de_esser.enabled:
            self.log.emit(f"    → 去齿音 …")
            self.stepChanged.emit(f"去齿音 (阈值 {cfg.de_esser.threshold_db}dB / 衰减 {cfg.de_esser.reduction_db}dB)")
            _log("  → 去齿音")
            data = self._de_ess(data, sr, cfg.de_esser)
            _log(f"  ← 去齿音完成, shape={data.shape}")

        # 防止削波
        peak = np.max(np.abs(data))
        if peak > 1.0:
            data /= peak * 1.0001

        _log(f"  写入输出: {os.path.basename(output_path)}")
        self._write(output_path, data, sr, original_dtype)
        self.log.emit(f"    ✓ 完成")
        _log(f"_process_one 完成: {os.path.basename(input_path)}")

    # ── I/O ─────────────────────────────────────────────

    def _read(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            return self._read_video_audio(path)
        import soundfile as sf
        data, sr = sf.read(path, dtype='float32', always_2d=True)
        return data, sr

    @staticmethod
    def _read_video_audio(path: str):
        """用 ffmpeg 提取音频为临时 WAV → numpy。"""
        import soundfile as sf
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_name = tmp.name
        try:
            subprocess.run([
                _ffmpeg_path(), '-y', '-i', path,
                '-vn', '-acodec', 'pcm_s16le',
                '-ar', '44100', '-ac', '2',
                tmp_name
            ], capture_output=True, check=True)
            data, sr = sf.read(tmp_name, dtype='float32', always_2d=True)
            return data, sr
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @staticmethod
    def _write(path: str, data: np.ndarray, sr: int, ref_dtype):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        if np.issubdtype(ref_dtype, np.floating):
            out = data.astype(np.float32)
        else:
            info = np.iinfo(ref_dtype)
            out = (data * info.max).clip(info.min, info.max).astype(ref_dtype)
        import soundfile as sf
        sf.write(path, out, sr)

    # ── 模块一：缩短静音 ──────────────────────────────────

    def _shorten_silence(self, data: np.ndarray, sr: int,
                         cfg: SilenceShortenConfig) -> np.ndarray:
        """静音缩短 —— 保留式 + 智能边界淡化。

        - 峰值+ RMS 双重检测判定每帧是否为静音
        - 在检测到的静音段中保留 target + 首尾 guard，其余切除
        - 合并间距 < 100ms 的切除区间，只在大段边界做淡化
        - 避免呼吸/低能量段反复淡入淡出产生"水底冒泡"音
        """
        frame_len = int(sr * 0.005)          # 5 ms 帧
        if frame_len < 1:
            frame_len = 1
        n_frames = len(data) // frame_len

        # —— 逐帧双重检测 ——
        thresh_linear = 10.0 ** (cfg.threshold_db / 20.0)
        is_silent = np.zeros(n_frames, dtype=bool)

        for i in range(n_frames):
            chunk = data[i*frame_len:(i+1)*frame_len]
            peak = np.max(np.abs(chunk))
            rms  = np.sqrt(np.mean(chunk**2))
            is_silent[i] = (peak < thresh_linear * 1.3) and (rms < thresh_linear)

        target_samples = int(cfg.target_duration_ms / 1000.0 * sr)
        margin_samples = int(0.06 * sr)     # 60ms 余量
        guard_samples  = int(0.03 * sr)     # 30ms 保护边距
        fade_samples   = int(0.008 * sr)    # 8ms 淡化
        merge_gap      = int(0.10 * sr)     # 100ms 以内的切点合并

        # —— 收集所有切除区间 ——
        raw_cuts = []
        i = 0
        while i < n_frames:
            if is_silent[i]:
                j = i
                while j < n_frames and is_silent[j]:
                    j += 1
                seg_start = i * frame_len
                seg_end   = min(j * frame_len, len(data))
                seg_len   = seg_end - seg_start

                if target_samples > 0 and seg_len > target_samples + margin_samples:
                    keep_len = guard_samples + target_samples + guard_samples
                    if keep_len < seg_len:
                        raw_cuts.append((seg_start + keep_len, seg_end))
                i = j
            else:
                i += 1

        if not raw_cuts:
            return data

        # —— 合并相邻切除区间（间隔 < merge_gap 的合并）——
        merged_cuts = [raw_cuts[0]]
        for cut in raw_cuts[1:]:
            if cut[0] - merged_cuts[-1][1] < merge_gap:
                merged_cuts[-1] = (merged_cuts[-1][0], cut[1])
            else:
                merged_cuts.append(cut)

        # —— 只在合并后的大段边界做淡化 ——
        faded = data.copy()
        f_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)[:, np.newaxis]
        f_in  = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)[:, np.newaxis]

        for cut_start, cut_end in merged_cuts:
            # 切除起点之前：fade out
            if cut_start >= fade_samples:
                faded[cut_start - fade_samples:cut_start] *= f_out
            # 切除终点之后：fade in
            if cut_end + fade_samples <= len(data):
                faded[cut_end:cut_end + fade_samples] *= f_in

        # —— 构建 mask 并切除 ——
        keep = np.ones(len(data), dtype=bool)
        for cut_start, cut_end in merged_cuts:
            keep[cut_start:cut_end] = False

        return faded[keep]

    # ── 模块二：强制限幅 ──────────────────────────────────

    @staticmethod
    def _hard_limit(data: np.ndarray, cfg: HardLimiterConfig) -> np.ndarray:
        gain_linear = 10.0 ** (cfg.input_gain_db / 20.0)
        ceiling     = 10.0 ** (cfg.max_level_db / 20.0)
        data = data * gain_linear

        # 软拐点限幅 —— 用 tanh 平滑过渡，避免硬削波产生的谐波失真（电流音）
        knee = ceiling * 0.85          # 拐点从 85% 电平处开始
        abs_data = np.abs(data)
        above_knee = abs_data > knee
        if above_knee.any():
            # 只处理超过拐点的采样点
            x = abs_data[above_knee] - knee
            w = ceiling - knee          # 拐点宽度
            # tanh 软饱和：拐点以上平滑逼近 ceiling
            softened = knee + w * np.tanh(x / w)
            gain = softened / abs_data[above_knee]
            data[above_knee] *= gain

        return data

    # ── 模块三：均衡器 ────────────────────────────────────

    @staticmethod
    def _apply_eq(data: np.ndarray, sr: int, preset_index: int) -> np.ndarray:
        sos = build_eq_sos(preset_index, float(sr))
        if sos.size == 0:
            return data
        result = sig.sosfiltfilt(sos, data, axis=0)
        if preset_index == 0:  # 柔和高音提升：总输出 -1dB（仿 AU Master Gain）
            result *= 10.0 ** (-1.0 / 20.0)
        return result

    # ── 模块四：去齿音 / 高频平滑 ──────────────────────

    @staticmethod
    def _de_ess(data: np.ndarray, sr: int, cfg: DeEsserConfig) -> np.ndarray:
        """宽频带去齿音器 —— 检测 4-10kHz 齿音频段的能量，超标时衰减全频带。

        原理类似 DBX 902 / Waves DeEsser：
        1. 带通滤波提取 4-10kHz 齿音分量
        2. 计算齿音 RMS 包络
        3. 包络超过阈值时，按比例衰减全频带信号
        4. 用快起慢放的包络平滑避免呼吸效应
        """
        n_channels = data.shape[1]

        # —— 带通滤波器：4-10kHz 齿音检测频段 ——
        bq_hp = _bq_highpass(sr, 4000, 0.7)
        bq_lp = _bq_lowpass(sr, 10000, 0.7)
        sos_bp = _to_sos(np.vstack([bq_hp, bq_lp]))

        # 提取齿音分量（因果滤波，非零相位，保证实时检测方向正确）
        sibilance = sig.sosfilt(sos_bp, data, axis=0)

        # —— RMS 包络 ——
        window = int(sr * 0.003)  # 3ms 窗口（快响应）
        if window < 1:
            window = 1

        sib_mono = np.mean(sibilance**2, axis=1)
        # 用卷积做滑动 RMS
        kernel = np.ones(window, dtype=np.float32) / window
        env_sq = np.convolve(sib_mono, kernel, mode='same')
        env = np.sqrt(np.maximum(env_sq, 1e-12))

        # —— 阈值 & 增益衰减 ——
        thresh = 10.0 ** (cfg.threshold_db / 20.0)
        max_reduction = 10.0 ** (-cfg.reduction_db / 20.0)   # 最大衰减倍数

        # 对每个采样点计算所需的增益
        gain_1d = np.where(env > thresh, thresh / env, 1.0)
        gain_1d = np.maximum(gain_1d, max_reduction)

        # —— 包络平滑：快起慢放 ——
        attack_coef  = np.exp(-1.0 / (sr * 0.002))   # 2ms 起控
        release_coef = np.exp(-1.0 / (sr * 0.040))   # 40ms 释放

        smoothed = gain_1d.copy()
        for i in range(1, len(smoothed)):
            if smoothed[i] < smoothed[i - 1]:
                smoothed[i] = attack_coef * smoothed[i - 1] + (1 - attack_coef) * smoothed[i]
            else:
                smoothed[i] = release_coef * smoothed[i - 1] + (1 - release_coef) * smoothed[i]

        gain = np.tile(smoothed[:, np.newaxis], (1, n_channels))
        result = data * gain.astype(np.float32)
        makeup = 10.0 ** (cfg.makeup_gain_db / 20.0)
        return result * makeup

    # ── 模块五（新增）：降噪 ───────────────────────────

    @staticmethod
    def _noise_reduction(data: np.ndarray, sr: int, cfg: NoiseReductionConfig) -> np.ndarray:
        """频谱减法降噪 —— 优化版。

        1. STFT 分帧（大 hop 减少计算量）
        2. 取最安静的帧估计噪声频谱
        3. 每帧减去噪声频谱（软掩蔽）
        4. ISTFT 重建
        """
        n_channels = data.shape[1]
        n_fft = 2048
        hop = n_fft // 2  # 50% overlapping (vs 75%), 大幅减少帧数

        result = np.zeros_like(data)
        for ch in range(n_channels):
            ch_data = data[:, ch]
            # STFT
            _, _, Zxx = sig.stft(ch_data, fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
            mag = np.abs(Zxx)

            # 噪声估计：取每帧 RMS 最低的 15% 作为噪声轮廓
            frame_rms = np.sqrt(np.mean(mag**2, axis=0))
            noise_thresh = np.percentile(frame_rms, 15)
            noise_frames = frame_rms <= noise_thresh
            noise_profile = np.mean(mag[:, noise_frames], axis=1) if noise_frames.any() else np.zeros(mag.shape[0])

            # 降噪强度
            reduction_linear = 10.0 ** (cfg.reduction_db / 20.0)
            noise_profile *= reduction_linear

            # 软掩蔽：Wiener-like 增益
            gain = (mag - noise_profile[:, np.newaxis]) / np.maximum(mag, 1e-10)
            gain = np.clip(gain, 0.05, 1.0)

            smooth_win = max(2, int(sr * 0.010 / hop))
            gain = uniform_filter1d(gain, smooth_win, axis=1, mode='nearest')

            mag_clean = mag * gain
            # 直接用复数除法恢复相位，避免 arctan 计算
            phase_complex = Zxx / np.maximum(mag, 1e-10)
            _, ch_clean = sig.istft(mag_clean * phase_complex, fs=sr,
                                     nperseg=n_fft, noverlap=n_fft - hop)
            if len(ch_clean) < len(ch_data):
                ch_clean = np.pad(ch_clean, (0, len(ch_data) - len(ch_clean)))
            else:
                ch_clean = ch_clean[:len(ch_data)]
            result[:, ch] = ch_clean

        return result.astype(np.float32)

    # ── 模块六：动态压缩 ──────────────────────────────

    @staticmethod
    def _compressor(data: np.ndarray, sr: int, cfg: CompressorConfig) -> np.ndarray:
        """RMS 前馈压缩器 —— 规整动态范围，小声听得清、大声不破音。

        软拐点 + 快起慢放 + 自动补偿增益。
        置于 EQ 之后、去齿音之前。
        """
        n_channels = data.shape[1]

        # —— RMS 包络 ——
        window = int(sr * 0.005)  # 5ms RMS 窗口
        if window < 1:
            window = 1
        mono_sq = np.mean(data**2, axis=1)
        kernel = np.ones(window, dtype=np.float32) / window
        env_sq = np.convolve(mono_sq, kernel, mode='same')
        env_db = 10.0 * np.log10(np.maximum(env_sq, 1e-14))

        # —— 软拐点压缩曲线 ——
        thresh = cfg.threshold_db
        knee_width = 6.0                    # 6dB 软拐点宽度
        ratio = cfg.ratio
        knee_start = thresh - knee_width / 2

        gr_db = np.zeros_like(env_db)       # gain reduction in dB
        above_knee = env_db > knee_start

        # 硬拐点区域（高于 knee_start + knee_width）
        hard = env_db > (knee_start + knee_width)
        gr_db[hard] = (env_db[hard] - thresh) * (1.0 - 1.0 / ratio)

        # 软拐点区域
        soft = above_knee & ~hard
        excess = env_db[soft] - knee_start
        gr_db[soft] = excess**2 / (2.0 * knee_width) * (1.0 - 1.0 / ratio)

        gr_linear = 10.0 ** (-gr_db / 20.0)

        # —— attack / release 平滑 ——
        if cfg.attack_ms > 0:
            attack_coef = np.exp(-1.0 / (sr * cfg.attack_ms / 1000.0))
        else:
            attack_coef = 0.0  # 瞬间起控
        release_coef = np.exp(-1.0 / (sr * cfg.release_ms / 1000.0))

        smoothed = gr_linear.copy()
        for i in range(1, len(smoothed)):
            if smoothed[i] < smoothed[i - 1]:
                smoothed[i] = attack_coef * smoothed[i - 1] + (1.0 - attack_coef) * smoothed[i]
            else:
                smoothed[i] = release_coef * smoothed[i - 1] + (1.0 - release_coef) * smoothed[i]

        gain = np.tile(smoothed[:, np.newaxis], (1, n_channels))
        result = data * gain.astype(np.float32)
        makeup = 10.0 ** (cfg.makeup_gain_db / 20.0)
        result *= makeup

        return result


# ═══════════════════════════════════════════════════════════
# Theme Helpers
# ═══════════════════════════════════════════════════════════

def _dim_border() -> str:
    return "#555555" if isDarkTheme() else "#d0d0d0"

def _hover_bg() -> str:
    return "rgba(255,255,255,0.05)" if isDarkTheme() else "rgba(0,0,0,0.03)"

def _disabled_bg() -> str:
    return "rgba(255,255,255,0.03)" if isDarkTheme() else "rgba(0,0,0,0.03)"


# ═══════════════════════════════════════════════════════════
# FileDropPanel
# ═══════════════════════════════════════════════════════════

class FileDropPanel(QFrame):
    filesChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fileDropPanel")
        self.setAcceptDrops(True)
        self.setMinimumWidth(260)
        self.setMaximumWidth(320)
        self._files: List[str] = []
        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)

        # 标题行
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = StrongBodyLabel("音视频文件", self)
        title_row.addWidget(title)
        title_row.addStretch()
        root.addLayout(title_row)

        self._count_label = CaptionLabel("未选择文件", self)
        root.addWidget(self._count_label)

        # 拖拽区域
        self._drop_zone = QFrame(self)
        self._drop_zone.setObjectName("dropZone")
        self._drop_zone.setMinimumHeight(100)
        self._drop_zone.setCursor(Qt.PointingHandCursor)
        dz_lay = QVBoxLayout(self._drop_zone)
        dz_lay.setAlignment(Qt.AlignCenter)
        dz_lay.setSpacing(8)
        dz_icon = QLabel("\U0001F4C1", self._drop_zone)
        dz_icon.setStyleSheet("font-size: 32px; border: none; background: transparent;")
        dz_icon.setAlignment(Qt.AlignCenter)
        dz_text = CaptionLabel("拖拽音视频文件到此处\n或点击下方按钮选择", self._drop_zone)
        dz_text.setAlignment(Qt.AlignCenter)
        dz_text.setWordWrap(True)
        dz_text.setStyleSheet("border: none; background: transparent; color: palette(text);")
        dz_lay.addWidget(dz_icon)
        dz_lay.addWidget(dz_text)
        root.addWidget(self._drop_zone)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._select_btn = TransparentPushButton("选择文件", self)
        self._select_btn.clicked.connect(self._on_select_files)
        self._clear_btn = TransparentPushButton("清空列表", self)
        self._clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self._select_btn)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # 替换原文件复选框
        self._replace_cb = CheckBox("替换原文件（不生成 _lele 副本）", self)
        self._replace_cb.stateChanged.connect(self._on_replace_toggled)
        root.addWidget(self._replace_cb)
        root.addSpacing(4)

        # 文件列表
        self._list_widget = QListWidget(self)
        self._list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self._list_widget, 1)

        # 处理进度条（默认隐藏）
        self._progress_frame = QFrame(self)
        self._progress_frame.setObjectName("progressFrame")
        self._progress_frame.setVisible(False)
        pf_lay = QVBoxLayout(self._progress_frame)
        pf_lay.setContentsMargins(0, 4, 0, 0); pf_lay.setSpacing(6)

        self._progress_bar = ProgressBar(self._progress_frame)
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)

        self._progress_label = CaptionLabel("准备处理 …", self._progress_frame)
        pf_lay.addWidget(self._progress_bar)
        pf_lay.addWidget(self._progress_label)
        root.addWidget(self._progress_frame)

        # 超链接 — 用普通标签 + 点击事件，避免 Qt 蓝色默认链接色
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        link_label = QLabel("B站：剪辑科学家", self)
        link_label.setAlignment(Qt.AlignCenter)
        link_label.setCursor(Qt.PointingHandCursor)
        link_label.setStyleSheet(
            "border: none; background: transparent; font-size: 12px; "
            "color: #FF6B9D; font-weight: bold;")
        link_label.mousePressEvent = lambda _: (
            QDesktopServices.openUrl(QUrl("https://space.bilibili.com/243758920")))
        root.addWidget(link_label)

    def _apply_theme(self):
        c = themeColor().name(); dim = _dim_border()
        self.setStyleSheet(f"""#fileDropPanel {{
            border: 1px solid {dim};
            border-radius: 12px;
            background: palette(base);
        }}""")
        self._drop_zone.setStyleSheet(f"""
            #dropZone {{ border: 2px dashed {dim}; border-radius: 10px; background: {c}08; }}
            #dropZone:hover {{ border-color: {c}; background: {c}14; }}
        """)
        self._list_widget.setStyleSheet(f"""
            QListWidget {{ border: 1px solid {dim}; border-radius: 8px; background: palette(window); padding: 4px; outline: none; }}
            QListWidget::item {{ padding: 5px 8px; border-radius: 4px; }}
            QListWidget::item:selected {{ background: {c}28; color: palette(text); }}
        """)

    # ── 拖拽 ──────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            if any(self._is_supported(p) for p in paths):
                event.acceptProposedAction()
                c = themeColor().name()
                self._drop_zone.setStyleSheet(
                    self._drop_zone.styleSheet()
                    .replace(f"background: {c}08", f"background: {c}1A")
                    .replace("dashed", "solid"))
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._apply_theme(); event.accept()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        valid = [p for p in paths if self._is_supported(p)]
        if valid:
            self._add_files(valid)
        self._apply_theme()
        event.acceptProposedAction()

    # ── 文件操作 ──────────────────────────────────────

    def _on_select_files(self):
        exts = sorted(SUPPORTED_EXTENSIONS)
        filter_str = "音视频文件 (" + " ".join(f"*{e}" for e in exts) + ");;所有文件 (*)"
        paths, _ = QFileDialog.getOpenFileNames(self, "选择音视频文件", "", filter_str)
        if paths:
            self._add_files([os.path.normpath(p) for p in paths])

    def _on_replace_toggled(self, checked):
        if checked:
            QMessageBox.warning(
                self, "提示",
                "已开启“替换原文件”模式！\n\n"
                "处理后的音频将直接覆盖原始文件，\n"
                "请务必提前备份原始声音，以防丢失。",
            )

    def _on_clear(self):
        self._files.clear(); self._list_widget.clear()
        self._count_label.setText("未选择文件")
        self.filesChanged.emit([])

    def _add_files(self, paths: List[str]):
        added = False
        for p in paths:
            if p not in self._files:
                self._files.append(p)
                item = QListWidgetItem(os.path.basename(p))
                item.setToolTip(p)
                self._list_widget.addItem(item)
                added = True
        if added:
            self._count_label.setText(f"已选 {len(self._files)} 个文件")
            self.filesChanged.emit(self._files)

    def get_files(self) -> List[str]:
        return list(self._files)

    def get_output_pairs(self) -> List[Tuple[str, str]]:
        pairs = []
        for p in self._files:
            if self._replace_cb.isChecked():
                out = p  # 直接替换原文件
            else:
                base, ext = os.path.splitext(p)
                out = f"{base}{OUTPUT_SUFFIX}{ext}"
            pairs.append((p, out))
        return pairs

    @staticmethod
    def _is_supported(path: str) -> bool:
        return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS

    # ── 进度 ──────────────────────────────────────────

    def show_progress(self, total: int):
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(0)
        self._progress_label.setText("准备处理 …")
        self._progress_frame.setVisible(True)

    def update_progress(self, current: int, total: int):
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(current)
        self._progress_label.setText(f"处理中 ({current}/{total})")

    def update_progress_step(self, text: str):
        self._progress_label.setText(text)

    def hide_progress(self):
        self._progress_bar.setValue(self._progress_bar.maximum())
        self._progress_label.setText("全部完成 ✓")
        self._progress_frame.setVisible(False)


# ═══════════════════════════════════════════════════════════
# SliderRow
# ═══════════════════════════════════════════════════════════

class SliderRow(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, label_text, min_val, max_val, default_val,
                 unit="", scale=1, decimal_places=0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._decimal_places = decimal_places
        self._unit = unit

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        self._label = BodyLabel(label_text, self)
        self._label.setFixedWidth(120)

        self._slider = Slider(self)
        self._slider.setOrientation(Qt.Horizontal)
        self._slider.setRange(min_val, max_val)
        self._slider.setValue(default_val)
        self._slider.setFixedWidth(240)
        self._slider.wheelEvent = lambda e: e.ignore()

        self._value_label = BodyLabel(self._fmt(default_val), self)
        self._value_label.setFixedWidth(72)
        self._value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self._label)
        layout.addWidget(self._slider)
        layout.addWidget(self._value_label)
        layout.addStretch()

        self._slider.valueChanged.connect(self._on_changed)

    def _fmt(self, raw: int) -> str:
        actual = raw / self._scale
        if self._decimal_places == 0:
            text = str(int(actual))
        else:
            text = f"{actual:.{self._decimal_places}f}"
        return f"{text} {self._unit}".strip()

    def _on_changed(self, value: int):
        self._value_label.setText(self._fmt(value))
        self.valueChanged.emit(value)

    def value(self) -> int:
        return self._slider.value()

    def setValue(self, value: int):
        self._slider.setValue(value)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self._label.setEnabled(enabled)
        self._slider.setEnabled(enabled)
        self._value_label.setEnabled(enabled)


# ═══════════════════════════════════════════════════════════
# EqPresetItem
# ═══════════════════════════════════════════════════════════

class EqPresetItem(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, index: int, title: str, description: str, parent=None):
        super().__init__(parent)
        self._index = index
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self._title_label = BodyLabel(title, self)
        self._desc_label = CaptionLabel(description, self)
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._title_label)
        layout.addWidget(self._desc_label)

        self._theme_color = themeColor().name()
        self._refresh_style()

    def setSelected(self, selected: bool):
        self._selected = selected; self._refresh_style()

    def isSelected(self) -> bool:
        return self._selected

    def _refresh_style(self):
        c = self._theme_color; dim = _dim_border()
        if not self.isEnabled():
            ss = f"EqPresetItem {{ border: 1px solid {dim}; border-radius: 8px; background: {_disabled_bg()}; }}"
        elif self._selected:
            ss = f"EqPresetItem {{ border: 2px solid {c}; border-radius: 8px; background: {c}18; }}"
        else:
            ss = f"EqPresetItem {{ border: 1px solid {dim}; border-radius: 8px; background: transparent; }}" \
                 f"EqPresetItem:hover {{ border: 1px solid #888888; background: {_hover_bg()}; }}"
        self.setStyleSheet(ss)
        self._title_label.setEnabled(self.isEnabled())
        self._desc_label.setEnabled(self.isEnabled())

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self._refresh_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit(self._index)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════
# AudioConfigDialog
# ═══════════════════════════════════════════════════════════

class AudioConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        _log("AudioConfigDialog.__init__ 开始")
        self.setWindowTitle("乐乐修音神器    微信：rpalele")
        self.resize(1020, 760)
        self.setMinimumSize(920, 680)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        self._active_eq_index = 0  # 柔和高音提升
        self._processor: Optional[AudioProcessor] = None
        self._build_ui()
        self._wire_signals()
        _log("AudioConfigDialog.__init__ 完成")

    def closeEvent(self, event):
        _log(f"closeEvent 被调用! 调用栈:\n{traceback.format_stack()}")
        super().closeEvent(event)

    def done(self, r):
        _log(f"done({r}) 被调用! 调用栈:\n{traceback.format_stack()}")
        super().done(r)

    def accept(self):
        _log(f"accept() 被调用! 调用栈:\n{traceback.format_stack()}")
        super().accept()

    def reject(self):
        _log(f"reject() 被调用! 调用栈:\n{traceback.format_stack()}")
        super().reject()

    # ── 布局 ──────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        self._build_hint_bar(root)
        body = QHBoxLayout(); body.setSpacing(16)

        self._file_panel = FileDropPanel(self)
        body.addWidget(self._file_panel)

        right = QVBoxLayout(); right.setSpacing(12)
        self._build_scroll_cards(right)
        self._build_button_row(right)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

    def _build_hint_bar(self, parent_layout):
        bar = QFrame(); bar.setObjectName("hintBar")
        c = themeColor().name()
        bar.setStyleSheet(f"#hintBar {{ background: {c}14; border: 1px solid {c}28; border-radius: 8px; }}")
        lay = QHBoxLayout(bar); lay.setContentsMargins(14, 10, 14, 10); lay.setSpacing(10)
        icon = QLabel("ℹ", bar)
        icon.setStyleSheet(f"font-size: 18px; color: {c}; border: none; background: transparent;")
        text = BodyLabel("启用的后处理将按顺序应用于所有生成的音频", bar)
        text.setStyleSheet("border: none; background: transparent;")
        lay.addWidget(icon); lay.addWidget(text); lay.addStretch()
        parent_layout.addWidget(bar)

    def _build_scroll_cards(self, parent_layout):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        container = QWidget()
        cards_layout = QVBoxLayout(container)
        cards_layout.setContentsMargins(0, 0, 0, 0); cards_layout.setSpacing(14)
        self._build_silence_card(cards_layout)
        self._build_noise_card(cards_layout)
        self._build_limiter_card(cards_layout)
        self._build_equalizer_card(cards_layout)
        self._build_compressor_card(cards_layout)
        self._build_deesser_card(cards_layout)
        # 缩短静音、降噪、去齿音默认关闭（AU 工作流中无此模块）
        self._silence_cb.setChecked(False)
        self._on_module_toggle(self._silence_card, self._silence_content, False)
        self._noise_cb.setChecked(False)
        self._on_module_toggle(self._noise_card, self._noise_content, False)
        self._deesser_cb.setChecked(False)
        self._on_module_toggle(self._deesser_card, self._deesser_content, False)
        cards_layout.addStretch()
        scroll.setWidget(container)
        parent_layout.addWidget(scroll, 1)

    # ── Card Factory ──────────────────────────────────

    def _create_card_frame(self, title: str, subtitle: str):
        card = QFrame(); card.setObjectName("moduleCard")
        main_lay = QVBoxLayout(card)
        main_lay.setContentsMargins(20, 16, 20, 16); main_lay.setSpacing(8)

        title_row = QHBoxLayout(); title_row.setSpacing(8)
        cb = CheckBox(title, card); cb.setChecked(True)
        title_row.addWidget(cb); title_row.addStretch()
        main_lay.addLayout(title_row)

        sub = CaptionLabel(subtitle, card); main_lay.addWidget(sub)

        content_lay = QVBoxLayout()
        content_lay.setSpacing(6); content_lay.setContentsMargins(4, 8, 4, 0)
        main_lay.addLayout(content_lay)

        self._apply_card_style(card, True)
        return card, cb, sub, content_lay

    def _apply_card_style(self, card: QFrame, checked: bool):
        c = themeColor().name(); dim = _dim_border()
        card.setStyleSheet(f"""#moduleCard {{
            border: {'2px solid ' + c if checked else '1px solid ' + dim};
            border-radius: 12px; background: palette(base);
        }}""")

    # ── 模块一 ─────────────────────────────────────────

    def _build_silence_card(self, parent_layout):
        card, cb, sub, content = self._create_card_frame("缩短静音", "将过长的静音段缩短到指定长度")
        self._silence_card = card; self._silence_cb = cb; self._silence_sub = sub
        self._silence_dur = SliderRow("目标静音时长", 0, 1000, 120, "ms", parent=card)
        self._silence_thr = SliderRow("静音阈值", -60, 0, -30, "dB", parent=card)
        content.addWidget(self._silence_dur); content.addWidget(self._silence_thr)
        self._silence_content = [self._silence_sub, self._silence_dur, self._silence_thr]
        parent_layout.addWidget(card)

    # ── 模块一B：降噪 ─────────────────────────────────

    def _build_noise_card(self, parent_layout):
        card, cb, sub, content = self._create_card_frame("降噪", "频谱减法降噪，去除底噪和电流声")
        self._noise_card = card; self._noise_cb = cb; self._noise_sub = sub
        self._noise_strength = SliderRow("降噪强度", 6, 20, 12, "dB", parent=card)
        content.addWidget(self._noise_strength)
        self._noise_content = [self._noise_sub, self._noise_strength]
        parent_layout.addWidget(card)

    # ── 模块二 ─────────────────────────────────────────

    def _build_limiter_card(self, parent_layout):
        card, cb, sub, content = self._create_card_frame("强制限幅", "限制音频峰值，防止爆音")
        self._limiter_card = card; self._limiter_cb = cb; self._limiter_sub = sub
        self._limiter_max  = SliderRow("最大电平", -120, 0, -10, "dB", scale=10, decimal_places=1, parent=card)
        self._limiter_gain = SliderRow("输入增益", -120, 120, 60, "dB", scale=10, decimal_places=1, parent=card)
        content.addWidget(self._limiter_max); content.addWidget(self._limiter_gain)
        self._limiter_content = [self._limiter_sub, self._limiter_max, self._limiter_gain]
        parent_layout.addWidget(card)

    # ── 模块三 ─────────────────────────────────────────

    def _build_equalizer_card(self, parent_layout):
        card, cb, sub, content = self._create_card_frame("均衡器", "调整音频频率特性")
        self._eq_card = card; self._eq_cb = cb; self._eq_sub = sub

        grid = QGridLayout(); grid.setSpacing(8)
        self._eq_items: List[EqPresetItem] = []
        for i, (title, desc) in enumerate(EQ_PRESETS):
            item = EqPresetItem(i, title, desc, card)
            item.clicked.connect(self._on_eq_clicked)
            row, col = divmod(i, 3)
            grid.addWidget(item, row, col)
            self._eq_items.append(item)
        self._eq_items[0].setSelected(True)  # 柔和高音提升
        content.addLayout(grid)
        self._eq_content = self._eq_items
        parent_layout.addWidget(card)

    # ── 模块四 ─────────────────────────────────────────

    def _build_compressor_card(self, parent_layout):
        card, cb, sub, content = self._create_card_frame("动态压缩", "规整音量动态，小声清晰、大声不破")
        self._comp_card = card; self._comp_cb = cb; self._comp_sub = sub
        self._comp_thr = SliderRow("压缩阈值", -500, 0, -100, "dB", scale=10, decimal_places=0, parent=card)
        self._comp_ratio = SliderRow("压缩比", 15, 80, 30, ":1", scale=10, decimal_places=1, parent=card)
        self._comp_gain = SliderRow("补偿增益", 0, 100, 0, "dB", scale=10, decimal_places=1, parent=card)
        content.addWidget(self._comp_thr); content.addWidget(self._comp_ratio)
        content.addWidget(self._comp_gain)
        self._comp_content = [self._comp_sub, self._comp_thr, self._comp_ratio, self._comp_gain]
        parent_layout.addWidget(card)

    # ── 模块五 ─────────────────────────────────────────

    def _build_deesser_card(self, parent_layout):
        card, cb, sub, content = self._create_card_frame("去齿音", "平滑高频齿音和嘶声，适配 TTS 配音")
        self._deesser_card = card; self._deesser_cb = cb; self._deesser_sub = sub
        self._deesser_thr = SliderRow("检测阈值", -500, -50, -300, "dB", scale=10, decimal_places=0, parent=card)
        self._deesser_red = SliderRow("衰减力度", 10, 120, 60, "dB", scale=10, decimal_places=0, parent=card)
        content.addWidget(self._deesser_thr); content.addWidget(self._deesser_red)
        self._deesser_content = [self._deesser_sub, self._deesser_thr, self._deesser_red]
        parent_layout.addWidget(card)

    # ── 按钮 ──────────────────────────────────────────

    def _build_button_row(self, parent_layout):
        row = QHBoxLayout(); row.setContentsMargins(0, 4, 0, 0); row.addStretch()
        self._help_btn = TransparentPushButton("帮助", self)
        self._help_btn.clicked.connect(self._show_help)
        self._reset_btn = TransparentPushButton("重置", self)
        self._reset_btn.setStyleSheet("""
            TransparentPushButton { color: #E74856; font-weight: bold; padding: 8px 20px; }
            TransparentPushButton:hover { background: rgba(231,72,86,0.08); }
        """)
        self._confirm_btn = PrimaryPushButton("确定", self)
        self._confirm_btn.setMinimumWidth(100)
        row.addWidget(self._help_btn); row.addSpacing(12)
        row.addWidget(self._reset_btn); row.addSpacing(12); row.addWidget(self._confirm_btn)
        parent_layout.addLayout(row)

    def _show_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("所有的参数均参考以下的设置")
        dialog.resize(650, 750)
        dialog.setMinimumSize(400, 400)
        layout = QVBoxLayout(dialog)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)

        import base64 as _b64
        for b64_data in [_help_img1_b64, _help_img2_b64, _help_img3_b64]:
            pixmap = QPixmap()
            pixmap.loadFromData(_b64.b64decode(b64_data))
            scaled = pixmap.scaledToWidth(580, Qt.SmoothTransformation)
            label = QLabel()
            label.setPixmap(scaled)
            label.setAlignment(Qt.AlignCenter)
            container_layout.addWidget(label)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)
        dialog.exec_()

    # ── 信号 ──────────────────────────────────────────

    def _wire_signals(self):
        self._silence_cb.toggled.connect(
            lambda on: self._on_module_toggle(self._silence_card, self._silence_content, on))
        self._limiter_cb.toggled.connect(
            lambda on: self._on_module_toggle(self._limiter_card, self._limiter_content, on))
        self._eq_cb.toggled.connect(
            lambda on: self._on_module_toggle(self._eq_card, self._eq_content, on))
        self._comp_cb.toggled.connect(
            lambda on: self._on_module_toggle(self._comp_card, self._comp_content, on))
        self._deesser_cb.toggled.connect(
            lambda on: self._on_module_toggle(self._deesser_card, self._deesser_content, on))
        self._noise_cb.toggled.connect(
            lambda on: self._on_module_toggle(self._noise_card, self._noise_content, on))
        self._reset_btn.clicked.connect(self._on_reset)
        self._confirm_btn.clicked.connect(self._on_confirm)

    # ── 交互 ──────────────────────────────────────────

    def _on_module_toggle(self, card, widgets, checked):
        self._apply_card_style(card, checked)
        for w in widgets:
            w.setEnabled(checked)

    def _on_eq_clicked(self, index: int):
        self._active_eq_index = index
        for i, item in enumerate(self._eq_items):
            item.setSelected(i == index)

    def _on_reset(self):
        self._silence_cb.setChecked(False)
        self._on_module_toggle(self._silence_card, self._silence_content, False)
        self._silence_dur.setValue(120); self._silence_thr.setValue(-30)
        self._noise_cb.setChecked(False)
        self._on_module_toggle(self._noise_card, self._noise_content, False)
        self._noise_strength.setValue(12)
        self._limiter_cb.setChecked(True)
        self._limiter_max.setValue(-10); self._limiter_gain.setValue(60)
        self._eq_cb.setChecked(True)
        self._on_eq_clicked(12)
        self._comp_cb.setChecked(True)
        self._comp_thr.setValue(-100); self._comp_ratio.setValue(30); self._comp_gain.setValue(0)
        self._deesser_cb.setChecked(False)
        self._on_module_toggle(self._deesser_card, self._deesser_content, False)
        self._deesser_thr.setValue(-300); self._deesser_red.setValue(60)

    def _on_confirm(self):
        _log("_on_confirm 被点击")
        config = self._gather()
        pairs  = self._file_panel.get_output_pairs()

        if not pairs:
            QMessageBox.warning(self, "提示", "请先选择至少一个音视频文件。")
            return

        _log(f"开始处理 {len(pairs)} 个文件")
        # 显示进度条
        self._file_panel.show_progress(len(pairs))

        # 禁用按钮
        self._confirm_btn.setEnabled(False)
        self._reset_btn.setEnabled(False)

        # 打印信息
        print("=" * 60)
        print("  音频后处理 — 开始处理")
        print("=" * 60)
        print(f"  文件数: {len(pairs)}")
        for inp, out in pairs:
            print(f"    {os.path.basename(inp)}  →  {os.path.basename(out)}")
        print(f"  缩短静音: {'开' if config.silence_shorten.enabled else '关'} "
              f"(目标={config.silence_shorten.target_duration_ms}ms, 阈值={config.silence_shorten.threshold_db}dB)")
        print(f"  强制限幅: {'开' if config.hard_limiter.enabled else '关'} "
              f"(最大={config.hard_limiter.max_level_db}dB, 增益={config.hard_limiter.input_gain_db:+.1f}dB)")
        print(f"  动态压缩: {'开' if config.compressor.enabled else '关'} "
              f"(阈值={config.compressor.threshold_db}dB, {config.compressor.ratio:.1f}:1, 补偿={config.compressor.makeup_gain_db:+.1f}dB)")
        print(f"  均衡器:   {'开' if config.equalizer.enabled else '关'} "
              f"(预设={EQ_PRESETS[config.equalizer.preset_index][0]})")
        print(f"  去齿音:   {'开' if config.de_esser.enabled else '关'} "
              f"(阈值={config.de_esser.threshold_db}dB, 衰减={config.de_esser.reduction_db}dB)")
        print("-" * 60)

        # 后台处理
        self._processor = AudioProcessor(pairs, config, self)
        self._processor.progress.connect(self._file_panel.update_progress)
        self._processor.stepChanged.connect(self._file_panel.update_progress_step)
        self._processor.log.connect(lambda msg: print(f"  {msg}"))
        self._processor.finished.connect(self._on_processing_done)
        _log("启动 AudioProcessor 线程...")
        self._processor.start()

    def _on_processing_done(self):
        _log("_on_processing_done 被调用")
        try:
            print("=" * 60)
            print("  全部处理完成 ✓")
            print("=" * 60)
            self._file_panel.hide_progress()
            self._confirm_btn.setEnabled(True)
            self._reset_btn.setEnabled(True)
            _log("_on_processing_done 完成，对话框仍在运行")
        except Exception as e:
            _log(f"_on_processing_done 异常: {e}\n{traceback.format_exc()}")

    def _gather(self) -> AudioConfig:
        return AudioConfig(
            silence_shorten=SilenceShortenConfig(
                enabled=self._silence_cb.isChecked(),
                target_duration_ms=self._silence_dur.value(),
                threshold_db=self._silence_thr.value(),
            ),
            hard_limiter=HardLimiterConfig(
                enabled=self._limiter_cb.isChecked(),
                max_level_db=self._limiter_max.value() / 10.0,
                input_gain_db=self._limiter_gain.value() / 10.0,
            ),
            equalizer=EqualizerConfig(
                enabled=self._eq_cb.isChecked(),
                preset_index=self._active_eq_index,
            ),
            compressor=CompressorConfig(
                enabled=self._comp_cb.isChecked(),
                threshold_db=self._comp_thr.value() / 10.0,
                ratio=self._comp_ratio.value() / 10.0,
                makeup_gain_db=self._comp_gain.value() / 10.0,
            ),
            de_esser=DeEsserConfig(
                enabled=self._deesser_cb.isChecked(),
                threshold_db=self._deesser_thr.value() / 10.0,
                reduction_db=self._deesser_red.value() / 10.0,
            ),
            noise_reduction=NoiseReductionConfig(
                enabled=self._noise_cb.isChecked(),
                reduction_db=float(self._noise_strength.value()),
            ),
        )


# ═══════════════════════════════════════════════════════════
# Entry Point
# ── 帮助图片 base64 ──────────────────────────────────
_help_img1_b64 = "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"

_help_img2_b64 = "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"

_help_img3_b64 = "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"

# ═══════════════════════════════════════════════════════════

def main():
    _log("main() 入口")
    try:
        app = QApplication(sys.argv)
        _log("QApplication 创建完成")

        # 内置图标（base64 编码，无需外部文件）
        import base64 as _b64
        _ico_data = _b64.b64decode(
            "AAABAAEAEBAAAAAAIACIAgAAFgAAAIlQTkcNChoKAAAADUlIRFIAAAAQAAAAEAgGAAAAH/P/YQAAAk9JREFUeJx1k81qVEEQhb/qezOOxoCJIRMTVBRcJGKIEZcxCiq6UQO6EjeKvknyChIJLl34AoILXYi6MCbgQhBEEMRRBINgnJn700e67zgTBRu6qe6uOtXndJV5Q0BcfOIgGYgbUwllifl4jQ+LhXvD+RKrjrEegFVewTGYf85cfSdKE2QJdFr4IicROFUIaQVj1ROmp+DKZfzUNMnIMIw10N69MDYKg0Po4wds7iS2+b0boy6AS1BRoIUFWFrGfIHMxQkler0OX77B2zdYp9VPGLkZ8okLjJWfP6us+Un53KzyiYaKeysqO21lRw4rB3VArVqqwplinKGQokIM4+o13PgkttXGf/4KL1/gazuwxmRMGJxdVmBd/n0N1H3RgUlUlnDxAu7oFDo2Uznfugmn5tHOHbhmE63ex/JsG4U0qSisrqgtKZdUSiqCXeZxH+0wv35WObirouBM1TdaXPCDQzA7A8N70O4hktML6PYdWF7CP3kKRY6trZNs/QRX/QJ/kApD2b5xZbOzUbAszMuXYuZicTEK2DlxXO0L51TUUnkzlS6I2P1Pq9Xh8SNsYwNuXI/0kolxzHuK+gAuSeH5M9JHj2HxCj5kT9KuiEHHvIM1v6H9P1AtJXn4gHL+DDhHstVCvsBereGnZ3Cbm13texSIFNojw8obY8rSAWUrd9Vp/1Ln/TtlBw8pM1NerysbHVEBKrt10OuF0ADeb+uDcDQ5Ab9aKGR0DuSrJooV6qNvH2B7QQV+IaCMPdhXvNc320L+Avh3xKyhyv7v8htEeld035eLmgAAAABJRU5ErkJggg=="
        )
        from PyQt5.QtGui import QPixmap
        _pm = QPixmap()
        _pm.loadFromData(_ico_data)
        app.setWindowIcon(QIcon(_pm))
        setTheme(Theme.AUTO)
        setThemeColor("#0078D4")
        font = QFont("Microsoft YaHei UI", 10)
        app.setFont(font)
        FluentStyleSheet.FLUENT_WINDOW.apply(app)

        dialog = AudioConfigDialog()
        dialog.setModal(True)
        dialog.finished.connect(app.quit)
        dialog.show()
        _log("进入 app.exec_() 主循环")
        ret = app.exec_()
        _log(f"app.exec_() 返回 {ret}，程序正常退出")
    except Exception:
        _log(f"main() 未捕获异常:\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
