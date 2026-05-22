# -*- coding: utf-8 -*-
"""Video compression using ffmpeg, target < 20MB."""
import os
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path


def _no_console():
    """Return kwargs to suppress console flash on Windows."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si}
    return {}


def get_ffmpeg_path():
    """Find ffmpeg executable: local ffmpeg folder > imageio-ffmpeg > system PATH."""
    import sys

    try:
        # Resolve base directory (works both from source and PyInstaller --onedir)
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys._MEIPASS)
        else:
            base_dir = Path(__file__).parent.parent

        # 1. Check ffmpeg/ folder next to app
        local_ffmpeg = base_dir / "ffmpeg" / "ffmpeg.exe"
        if not local_ffmpeg.exists():
            local_ffmpeg = base_dir / "ffmpeg" / "ffmpeg"
        if local_ffmpeg.exists():
            return str(local_ffmpeg)
        # 2. Check imageio-ffmpeg
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
        # 3. System PATH
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        raise RuntimeError("ffmpeg not found. Place ffmpeg.exe in the ffmpeg/ folder next to the app, or install: pip install imageio-ffmpeg")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"查找ffmpeg时发生异常: {e}") from e


def get_video_duration(ffmpeg_path, input_path):
    """Get video duration in seconds. Tries ffprobe first, falls back to ffmpeg stderr parse."""
    # Try ffprobe first
    ffprobe = ffmpeg_path.replace("ffmpeg", "ffprobe")
    if not os.path.exists(ffprobe):
        ffprobe = ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
    if os.path.exists(ffprobe):
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", input_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, **_no_console())
            return float(result.stdout.strip())
        except Exception:
            pass

    # Fallback: parse ffmpeg -i stderr for "Duration: HH:MM:SS.ms"
    try:
        result = subprocess.run(
            [ffmpeg_path, "-i", input_path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, **_no_console())
        for line in result.stderr.split("\n"):
            if "Duration:" in line:
                # "  Duration: 00:01:23.45, start: ..."
                dur_str = line.strip().split("Duration: ")[1].split(",")[0]
                h, m, s = dur_str.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 0


def compress_video(input_path, target_mb=20, progress_callback=None):
    """
    Compress video to under target_mb MB using progressive strategy.

    Returns the path to the compressed file, or the original if already small enough.

    Strategy:
    1. If file already < target_mb, return original path
    2. Try CRF 28 with half resolution, remove audio
    3. If still too large, increase CRF progressively (32, 36, 40)
    4. If still too large, further reduce resolution
    """
    try:
        size_mb = os.path.getsize(input_path) / (1024 * 1024)
        if size_mb <= target_mb:
            return input_path

        ffmpeg = get_ffmpeg_path()
        output_path = os.path.join(tempfile.gettempdir(), Path(input_path).stem + "_compressed.mp4")
        duration = get_video_duration(ffmpeg, input_path)

        # Progressive compression: scale down + increase CRF
        scale_presets = [
            "854:480",    # 480p
            "640:360",    # 360p
            "426:240",    # 240p
        ]

        for scale in scale_presets:
            for crf in [28, 32, 36, 40]:
                if progress_callback:
                    progress_callback(f"Compressing: CRF={crf}, scale={scale}")

                cmd = [
                    ffmpeg, "-y",
                    "-i", input_path,
                    "-vf", f"scale={scale}",
                    "-r", "15",
                    "-crf", str(crf),
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-an",  # remove audio
                    output_path
                ]
                try:
                    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, **_no_console())
                except subprocess.TimeoutExpired:
                    continue

                if os.path.exists(output_path):
                    new_size = os.path.getsize(output_path) / (1024 * 1024)
                    if progress_callback:
                        progress_callback(f"Compressed: {new_size:.1f}MB")
                    if new_size < target_mb:
                        return output_path
                    # Clean up and try next
                    os.remove(output_path)

        # Last resort: return whatever we got on the final attempt
        # Re-run with most aggressive settings
        cmd = [
            ffmpeg, "-y",
            "-i", input_path,
            "-vf", "scale=426:240",
            "-r", "10",
            "-crf", "40",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-an",
            output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, **_no_console())
        except subprocess.TimeoutExpired:
            if progress_callback:
                progress_callback("最后压缩尝试超时，使用原文件")
            return input_path
        if os.path.exists(output_path):
            return output_path
        return input_path
    except Exception as e:
        import sys
        print(f"[ERROR] 视频压缩异常: {e}", file=sys.stderr)
        if progress_callback:
            progress_callback(f"压缩异常: {e}，使用原文件")
        return input_path


def extract_thumbnail(input_path, output_path=None, time_offset=2):
    """Extract a thumbnail image from video at given time offset.

    Returns the path to the thumbnail JPEG, or None on failure.
    Errors are logged to stderr instead of being silently swallowed.
    """
    import sys as _sys
    try:
        ffmpeg = get_ffmpeg_path()
    except RuntimeError as e:
        print(f"[ERROR] 提取缩略图失败 - ffmpeg未找到: {e}", file=_sys.stderr)
        return None

    if output_path is None:
        output_path = os.path.join(tempfile.gettempdir(), Path(input_path).stem + "_thumb.jpg")

    if os.path.exists(output_path):
        return output_path

    cmd = [
        ffmpeg, "-y",
        "-ss", str(time_offset),
        "-i", input_path,
        "-vframes", "1",
        "-q:v", "5",
        output_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, **_no_console())
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        else:
            print(f"[WARN] 缩略图未生成: {os.path.basename(input_path)} stderr={result.stderr[:200]}", file=_sys.stderr)
            return None
    except subprocess.TimeoutExpired:
        print(f"[WARN] 缩略图提取超时: {os.path.basename(input_path)}", file=_sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] 缩略图提取异常: {os.path.basename(input_path)} — {e}", file=_sys.stderr)
        return None
