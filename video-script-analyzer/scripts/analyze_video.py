# -*- coding: utf-8 -*-
"""
视频分镜脚本分析器（单视频版本）
将视频文件通过 Gemini API 分析，生成逐帧漫剧分镜脚本
使用方式: python analyze_video.py [视频路径] [输出路径] [API地址] [API密钥] [模型名] [集数]
"""
import requests
import json
import base64
import os
import sys
import time
import subprocess
import shutil

# requests库自动处理SSL，用verify=False绕过证书验证

# ============== 配置区（可通过参数覆盖） ==============
API_KEY = "sk-MuEiwKWLDIpAX68VCmxcZV6cwuHHQR102Qke5P6xKFgYOmRT"
API_BASE = "https://www.geeknow.top/v1"
MODEL = "gemini-3-pro-preview"
VIDEO_PATH = None
OUTPUT_PATH = None
EPISODE_NUM = None  # 集数，用于提示词

# 压缩配置：压缩后原始文件大小上限（base64膨胀约1.33倍，19MB原始≈25.3MB base64）
COMPRESS_TARGET_MB = 18
COMPRESS_CR = 28  # 压缩质量（CRF），数值越大压缩率越高

# ============== 提示词模板 ==============
PROMPT_TEMPLATE = """【角色设定】
你现在是一位经验丰富的漫剧（动态漫/微短剧）编剧和分镜导演。你擅长将小说文本或故事大纲转化为具有极强画面感、节奏紧凑的分镜脚本。

【任务目标】
请将我提供的视频，严格按照我指定的格式，拆解为镜头级别的漫剧分镜脚本。

【格式规范】（必须严格遵守！）
请按以下结构输出，不要遗漏任何层级：

第X集：[集数标题，概括本集核心看点]
[场景编号] [日/夜] [内/外景] [具体场景名称]
（例如：1.1 日 内 封闭仓库/陷阱区）
出场人物：[列出本场出现的角色，可带简短特征]

[正文拆解规则]：
必须交替使用"画面描述"和"台词/音效"，按镜头顺序推进。

【关键要求：每个镜头必须标注时长！】
画面描述必须以"▲画面："开头，紧跟"【时长X秒】"，然后括号内详细描述人物动作、表情、场景细节或特效，同时必须标注运镜方式。

标准格式示例：
▲画面：【时长5秒】（李刚眼神一凛，反手精准扣住光头反派的手腕，用力一折，顺势一记重拳砸向其面门）快速推镜头至李刚冷酷的脸庞，随后切至动作特写。
台词/音效：李刚（发力闷哼）：……

▲画面：【时长3秒】（固定中景，皮帽老头面色铁青，双手背后，嘴角抽搐）。
台词/音效：皮帽老头（咬牙切齿）：你等着……

运镜方式参考：固定镜头、推镜头、拉镜头、摇镜头、环绕运镜、跟拍、升降镜头、手持抖动、俯拍、仰拍、特写、大特写、远景、定格等。

台词格式：角色名（情绪/动作，发声方式）：台词内容。
发声方式说明：正常说话不标注，内心独白标为（os），画外音标为（旁白）。

【最高级别命令】
1. 请逐帧级别解析视频，精确估算每个镜头的持续时间（单位：秒），所有镜头时长累加应与视频总时长基本一致。
2. 运镜必须精确标出，例如：
   - 人物背对镜头→180度环绕运镜→转至人物正面
   - 从远景推进至特写
   - 镜头跟随人物移动
   每一个镜头切换都必须标注运镜变化。
3. 不要省略任何镜头，不要省略任何台词。

请现在开始完整拆解这个视频的第{episode}集内容。"""


def get_ffmpeg_path():
    """查找 ffmpeg 可执行文件路径"""
    # 尝试 imageio-ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    # 尝试系统 PATH
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    raise RuntimeError("ffmpeg not found. Install via: pip install imageio-ffmpeg")


def compress_video(input_path, target_mb=COMPRESS_TARGET_MB):
    """
    压缩视频，使压缩后文件小于 target_mb MB
    返回压缩后文件路径（同目录，加 .compressed.mp4 后缀）
    """
    import tempfile
    output_path = input_path.replace(".mp4", ".compressed.mp4")
    if output_path == input_path:
        output_path = input_path + ".compressed.mp4"

    ffmpeg = get_ffmpeg_path()
    sys.stdout.write(f"[INFO] Compressing video using: {ffmpeg}\n")
    sys.stdout.flush()

    # 获取原始码率，用于设置压缩码率上限
    probe_cmd = [
        ffmpeg.replace("ffmpeg.exe", "ffprobe.exe") if "ffmpeg.exe" in ffmpeg else ffmpeg.replace("ffmpeg", "ffprobe"),
        "-v", "error", "-show_entries", "format=bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1", input_path
    ]
    # 简单用 ffmpeg -i 获取信息（更可靠）
    # 直接用 CRF 模式，目标文件大小 ≈ target_mb
    # 码率估算: target_mb * 8 / duration_sec = bitrate_kbps
    # 用 CRF 更可靠，从低质量开始尝试
    duration_cmd = [
        ffmpeg, "-i", input_path, "-f", "null", "-"
    ]
    # 直接用两套参数：先试 CRF28，不够再降
    for crf in [COMPRESS_CR, 32, 36, 40]:
        scale = "360:640"
        cmd = [
            ffmpeg, "-y",
            "-i", input_path,
            "-vf", f"scale={scale}",
            "-r", "15",
            "-crf", str(crf),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "64k",
            output_path
        ]
        sys.stdout.write(f"[INFO] Compress attempt CRF={crf}, scale={scale}...\n")
        sys.stdout.flush()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            sys.stdout.write(f"[WARN] Compress timeout at CRF={crf}\n")
            continue

        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / 1024 / 1024
            sys.stdout.write(f"[INFO] Compressed size: {size_mb:.2f} MB (CRF={crf})\n")
            sys.stdout.flush()
            if size_mb < target_mb:
                return output_path
            # 如果还不够小，删除并用更高压缩比重试
            if crf == 40:  # 最后一轮仍然太大
                sys.stdout.write(f"[WARN] Cannot compress below {target_mb}MB, using best effort: {size_mb:.2f}MB\n")
                return output_path
            os.remove(output_path)

    if os.path.exists(output_path):
        return output_path
    raise RuntimeError("Compression failed: could not produce output file")


def is_size_error(e):
    """判断异常是否由文件过大引起"""
    msg = str(e).lower()
    return any(kw in msg for kw in [
        "too large", "too big", "maximum", "exceed", "413",
        "payload", "size", "26", "mb", "上传", "过大", "超过"
    ])


def run_analysis(video_path, output_path, api_base, api_key, model, episode_num):
    """执行视频分析主逻辑（先试原文件，失败则压缩重试）"""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # 构建提示词
    prompt = PROMPT_TEMPLATE.format(episode=episode_num) if episode_num else PROMPT_TEMPLATE.format(episode="")

    # 先尝试原文件；如果失败则压缩后重试
    current_video_path = video_path
    compressed_path = None
    already_compressed = False
    max_retries = 2  # 只试原文件+压缩各1次，快速跳过，不浪费时间

    for attempt in range(1, max_retries + 1):
        # 每次重试前重新读取当前视频文件（可能已被压缩替换）
        with open(current_video_path, "rb") as f:
            video_data = f.read()
        video_b64 = base64.b64encode(video_data).decode("utf-8")
        size_mb = len(video_data) / 1024 / 1024

        sys.stdout.write(f"[INFO] Attempt {attempt}/{max_retries} - Video: {size_mb:.2f} MB\n")
        sys.stdout.flush()

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:video/mp4;base64,{video_b64}"}}
                    ]
                }
            ],
            "max_tokens": 32000
        }

        req_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            sys.stdout.write(f"[INFO] Sending request (attempt {attempt}/{max_retries})...\n")
            sys.stdout.flush()

            # 使用 requests 库发送请求（自动处理大body、分块传输、SSL）
            api_url = f"{api_base}/chat/completions"
            resp = requests.post(
                api_url,
                data=req_data,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json; charset=utf-8"
                },
                timeout=600,
                verify=False
            )
            resp.raise_for_status()
            resp_data = resp.text

            result = json.loads(resp_data)
            content = result["choices"][0]["message"]["content"]

            # 保存结果
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

            sys.stdout.write(f"[OK] Saved to: {output_path}\n")
            sys.stdout.write(f"[OK] Total chars: {len(content)}\n")
            sys.stdout.flush()

            # 清理压缩后的临时文件
            if compressed_path and os.path.exists(compressed_path):
                os.remove(compressed_path)
            return
        except Exception as e:
            sys.stdout.write(f"[WARN] Attempt {attempt} failed: {type(e).__name__}: {e}\n")
            sys.stdout.flush()

            # 判断是否因文件过大失败，且尚未压缩过
            if not already_compressed and is_size_error(e):
                sys.stdout.write(f"[INFO] File may be too large, compressing...\n")
                sys.stdout.flush()
                try:
                    compressed_path = compress_video(current_video_path, target_mb=COMPRESS_TARGET_MB)
                    current_video_path = compressed_path
                    already_compressed = True
                    # 压缩成功后立即重试（不计入原重试次数上限，但最多压缩一次）
                    continue
                except Exception as comp_err:
                    sys.stdout.write(f"[ERROR] Compression failed: {comp_err}\n")
                    sys.stdout.flush()
                    raise

            if attempt < max_retries:
                # 短暂等待即可，不浪费时间重试
                wait = 5
                sys.stdout.write(f"[INFO] Waiting {wait}s before retry...\n")
                sys.stdout.flush()
                time.sleep(wait)
            else:
                sys.stdout.write(f"[ERROR] All {max_retries} attempts failed.\n")
                sys.stdout.flush()
                raise


if __name__ == "__main__":
    # 支持命令行参数
    # python analyze_video.py [视频路径] [输出路径] [API地址] [API密钥] [模型名] [集数]
    args = sys.argv[1:]

    if len(args) >= 1:
        VIDEO_PATH = args[0]
    if len(args) >= 2:
        OUTPUT_PATH = args[1]
    if len(args) >= 3:
        API_BASE = args[2]
    if len(args) >= 4:
        API_KEY = args[3]
    if len(args) >= 5:
        MODEL = args[4]
    if len(args) >= 6:
        EPISODE_NUM = args[5]

    if VIDEO_PATH is None or OUTPUT_PATH is None:
        sys.stdout.write("[ERROR] Usage: python analyze_video.py [video_path] [output_path] [api_base] [api_key] [model] [episode_num]\n")
        sys.stdout.flush()
        sys.exit(1)

    run_analysis(VIDEO_PATH, OUTPUT_PATH, API_BASE, API_KEY, MODEL, EPISODE_NUM)
