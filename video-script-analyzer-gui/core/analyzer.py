# -*- coding: utf-8 -*-
"""Video analysis logic — API 调用封装，支持重试机制"""
import json
import base64
import os
import re
import sys
import time
import traceback
import requests

from .compressor import compress_video

PROMPT_TEMPLATE = """【角色设定】
你现在是一位经验丰富的漫剧（动态漫/微短剧）编剧和分镜导演。你擅长将小说文本或故事大纲转化为具有极强画面感、节奏紧凑的分镜脚本。

【任务目标】
请将我提供的视频，严格按照我指定的格式，拆解为镜头级别的漫剧分镜脚本。

【格式规范】（必须严格遵守！）
请按以下结构输出，不要遗漏任何层级：

第X集：[集数标题，概括本集核心看点]
[场景编号] [日/夜] [内/外景] [具体场景名称]
出场人物：[列出本场出现的角色，可带简短特征]

[正文拆解规则]：
必须交替使用"画面描述"和"台词/音效"，按镜头顺序推进。

【关键要求：每个镜头必须标注时长！】
画面描述必须以"▲画面："开头，紧跟"【时长X秒】"，然后括号内详细描述人物动作、表情、场景细节或特效，同时必须标注运镜方式。

标准格式示例：
▲画面：【时长5秒】（李刚眼神一凛，反手精准扣住光头反派的手腕，用力一折，顺势一记重拳砸向其面门）快速推镜头至李刚冷酷的脸庞，随后切至动作特写。
台词/音效：李刚（发力闷哼）：……

运镜方式参考：固定镜头、推镜头、拉镜头、摇镜头、环绕运镜、跟拍、升降镜头、手持抖动、俯拍、仰拍、特写、大特写、远景、定格等。

台词格式：角色名（情绪/动作，发声方式）：台词内容。
发声方式说明：正常说话不标注，内心独白标为（os），画外音标为（旁白）。

【最高级别命令】
1. 请逐帧级别解析视频，精确估算每个镜头的持续时间（单位：秒），所有镜头时长累加应与视频总时长基本一致。
2. 运镜必须精确标出。
3. 不要省略任何镜头，不要省略任何台词。

请现在开始完整拆解这个视频的第{episode}集内容。"""

MAX_RETRIES = 3
REQUEST_TIMEOUT = 180


def extract_episode_number(filename):
    try:
        m = re.search(r'第(\d+)集', filename)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)', filename)
        if m:
            return int(m.group(1))
        return 0
    except Exception as e:
        print(f"[ERROR] 提取集数异常: {filename} — {e}", file=sys.stderr)
        return 0


def find_script_path(video_path, directory=None):
    try:
        if directory is None:
            directory = os.path.dirname(video_path)
        ep = extract_episode_number(os.path.basename(video_path))
        for f in os.listdir(directory):
            if '_分镜脚本' in f and f.endswith('.txt'):
                f_ep = extract_episode_number(f)
                if f_ep == ep:
                    return os.path.join(directory, f)
        base = os.path.splitext(os.path.basename(video_path))[0]
        script_path = os.path.join(directory, f"{base}_分镜脚本.txt")
        if os.path.exists(script_path):
            return script_path
        return None
    except OSError as e:
        print(f"[ERROR] 查找剧本文件异常: {e}", file=sys.stderr)
        return None


def analyze_video(video_path, api_config, output_dir=None,
                  progress_callback=None, log_callback=None):
    """分析单个视频，支持最多 3 次重试"""
    def log(msg, level="info"):
        if log_callback:
            log_callback(msg, level)

    try:
        return _analyze_video_impl(video_path, api_config, output_dir, progress_callback, log)
    except Exception as e:
        tb = traceback.format_exc()
        log(f"分析器内部异常: {e}\n{tb[:800]}", "error")
        return False, f"分析器内部异常: {e}", None


def _analyze_video_impl(video_path, api_config, output_dir, progress_callback, log):
    """analyze_video 的实际实现"""
    if not os.path.exists(video_path):
        return False, f"文件未找到: {video_path}", None

    if output_dir is None:
        output_dir = os.path.dirname(video_path)

    ep = extract_episode_number(os.path.basename(video_path))
    output_filename = f"{ep}集_分镜脚本.txt" if ep else f"{os.path.splitext(os.path.basename(video_path))[0]}_分镜脚本.txt"
    output_path = os.path.join(output_dir, output_filename)

    if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
        log(f"第{ep}集: 已存在分析结果，跳过", "success")
        return True, "已分析（跳过）", output_path

    base_url = api_config.get("base_url", "https://www.geeknow.top/v1")
    api_key = api_config.get("api_key", "")
    model = api_config.get("model", "gemini-3-pro-preview")
    custom_prompt = api_config.get("custom_prompt", "")

    # 压缩（超过 20MB）
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    current_path = video_path
    compressed_path = None


    if file_size_mb > 20:
        msg = f"第{ep}集: 文件 {file_size_mb:.1f}MB > 20MB，开始压缩..."
        log(msg, "info")
        if progress_callback:
            progress_callback("正在压缩视频...", 10)
        try:
            compressed_path = compress_video(video_path, target_mb=20)
            current_path = compressed_path
            new_mb = os.path.getsize(current_path) / (1024 * 1024)
            log(f"第{ep}集: 压缩完成 ({new_mb:.1f}MB)", "info")
            if progress_callback:
                progress_callback(f"压缩完成 ({new_mb:.1f}MB)", 20)
        except Exception as e:
            log(f"第{ep}集: 压缩失败 — {e}，使用原文件", "error")

            if progress_callback:
                progress_callback(f"压缩失败，使用原文件", 20)

    # 大小安全检查：超过 80MB 拒绝编码，避免 OOM 导致进程静默崩溃
    file_mb = os.path.getsize(current_path) / (1024 * 1024)

    if file_mb > 80:
        msg = f"视频文件过大 ({file_mb:.1f}MB > 80MB)，压缩后仍超出限制，无法分析"
        log(msg, "error")
        if progress_callback:
            progress_callback(msg, 0)
        if compressed_path and compressed_path != video_path and os.path.exists(compressed_path):
            try:
                os.remove(compressed_path)
            except Exception:
                pass
        return False, msg, None

    # 读取并编码视频
    if progress_callback:
        progress_callback("正在读取视频文件...", 25)
    with open(current_path, "rb") as f:
        video_data = f.read()
    video_b64 = base64.b64encode(video_data).decode("utf-8")
    del video_data  # 释放原始字节，降低峰值内存

    # 提示词
    if custom_prompt.strip():
        prompt = custom_prompt.strip()
        log(f"第{ep}集: 使用自定义指令", "info")
    else:
        prompt = PROMPT_TEMPLATE.format(episode=f"第{ep}集" if ep else "")

    # 附加集数信息
    if ep:
        prompt += f"\n附加要求：这是第{ep}集"

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

    api_url = f"{base_url}/chat/completions"


    # ── 重试循环 ──
    last_error = ""
    should_wait = False  # only wait for timeout/connection errors
    for attempt in range(1, MAX_RETRIES + 1):
        if progress_callback:
            pct = 30 + (attempt - 1) * 20
            progress_callback(f"第 {attempt}/{MAX_RETRIES} 次尝试...", pct)

        log(f"第{ep}集: 第 {attempt}/{MAX_RETRIES} 次 API 请求 ({REQUEST_TIMEOUT}s 超时)", "info")


        try:
            resp = requests.post(
                api_url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json; charset=utf-8"
                },
                timeout=REQUEST_TIMEOUT,
                verify=False
            )


            resp.raise_for_status()
            result = resp.json()
            content = result["choices"][0]["message"]["content"]

            # 修正集数：将第X集、第几集等占位符替换为实际集数
            if ep:
                content = re.sub(r'第[几XxX\d]+集', f'第{ep}集', content)
                # 处理标题格式 "第N集：" 前后可能不一致的情况
                content = re.sub(r'^第\d+集', f'第{ep}集', content, flags=re.MULTILINE)

            # 保存结果
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

            if compressed_path and compressed_path != video_path and os.path.exists(compressed_path):
                try:
                    os.remove(compressed_path)
                except Exception:
                    pass

            if progress_callback:
                progress_callback("分析完成！", 100)
            log(f"第{ep}集: 分析成功！({len(content)} 字)", "success")
            return True, f"成功（{len(content)} 字）", output_path

        except requests.exceptions.Timeout:
            last_error = f"请求超时 ({REQUEST_TIMEOUT}s)"
            should_wait = True


            log(f"第{ep}集 第{attempt}次: {last_error}", "warning")
        except requests.exceptions.ConnectionError as e:
            last_error = f"连接失败: {e}"
            should_wait = True


            log(f"第{ep}集 第{attempt}次: {last_error}", "warning")
        except requests.exceptions.HTTPError as e:
            body = ""
            try:
                body = e.response.text[:500] if e.response else ""
            except Exception:
                pass
            sc = e.response.status_code if e.response else '?'
            last_error = f"HTTP {sc}"
            should_wait = False


            log(f"第{ep}集 第{attempt}次: HTTP {sc} — {body}", "warning")
        except Exception as e:
            last_error = str(e)
            should_wait = False
            tb = traceback.format_exc()


            log(f"第{ep}集 第{attempt}次: {last_error}\n{tb[:500]}", "warning")

        if attempt < MAX_RETRIES:
            if should_wait:
                wait = attempt * 10
                log(f"第{ep}集: 等待 {wait}s 后重试...", "info")
                if progress_callback:
                    progress_callback(f"等待 {wait}s 后重试...", 30 + attempt * 20)
                time.sleep(wait)
            else:
                log(f"第{ep}集: 立即重试...", "info")

    log(f"第{ep}集: 全部 {MAX_RETRIES} 次尝试均失败 — {last_error}", "warning")


    if progress_callback:
        progress_callback(f"失败: {last_error}", 0)
    return False, f"重试{MAX_RETRIES}次后失败: {last_error}", None
