# -*- coding: utf-8 -*-
"""
批量视频分镜脚本分析器 v3
- 调用 analyze_video.py 处理每个视频（自带压缩重试逻辑）
- 支持多文件夹，按顺序依次处理
- 自动跳过已分析的集数
- 用法: python batch_analyze.py <目录1> [目录2] [目录3] ...
        若不提供参数，则使用脚本内 VIDEO_DIRS 列表
"""
import subprocess
import os
import sys
import time
import re
import datetime

# 修复Windows重定向时的编码问题 (Python 3.7+)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ============== 配置 ==============
ANALYZE_SCRIPT = r"C:\Users\Administrator\.workbuddy\skills\video-script-analyzer\scripts\analyze_video.py"
VENV_PYTHON  = r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
API_BASE      = "https://www.geeknow.top/v1"
API_KEY       = "sk-MuEiwKWLDIpAX68VCmxcZV6cwuHHQR102Qke5P6xKFgYOmRT"
MODEL         = "gemini-3-pro-preview"

# 默认处理目录（命令行未提供时使用）
VIDEO_DIRS = [
    r"C:\Users\Administrator\Downloads\win-x64\cache\七零打猎，我让野猪排队撞树",
    r"C:\Users\Administrator\Downloads\win-x64\cache\五十岁，我的人生刚刚开火",
    r"C:\Users\Administrator\Downloads\win-x64\cache\人间难小满",
    r"C:\Users\Administrator\Downloads\win-x64\cache\大壮重回80",
]

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_log.txt")
FAILED_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "failed_episodes.txt")


def log(msg, console=True):
    """写日志到文件（UTF-8），可选打印到控制台"""
    line = msg if msg.endswith("\n") else msg + "\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    if console:
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            print(repr(msg), flush=True)


def extract_episode_number(filename):
    m = re.search(r'第(\d+)集', filename)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)', filename)
    if m:
        return int(m.group(1))
    return None


def get_already_analyzed(directory):
    analyzed = set()
    if not os.path.isdir(directory):
        return analyzed
    for f in os.listdir(directory):
        if '_分镜脚本' in f and f.endswith('.txt'):
            ep = extract_episode_number(f)
            if ep:
                analyzed.add(ep)
    return analyzed


def find_mp4_files(directory):
    """返回 [(ep_num, filename, full_path)] 按集数排序"""
    results = []
    if not os.path.isdir(directory):
        log(f"[WARN] 目录不存在: {directory}")
        return results
    for f in os.listdir(directory):
        if f.lower().endswith('.mp4'):
            ep = extract_episode_number(f)
            if ep is not None:
                results.append((ep, f, os.path.join(directory, f)))
    results.sort(key=lambda x: x[0])
    return results


def process_video(video_path, output_path, episode_num, log_prefix=""):
    """
    调用 analyze_video.py 处理单个视频
    返回 (success: bool, message: str)
    """
    if not os.path.exists(VENV_PYTHON):
        return False, f"venv python not found: {VENV_PYTHON}"
    if not os.path.exists(ANALYZE_SCRIPT):
        return False, f"analyze script not found: {ANALYZE_SCRIPT}"

    cmd = [
        VENV_PYTHON, ANALYZE_SCRIPT,
        video_path,
        output_path,
        API_BASE,
        API_KEY,
        MODEL,
        str(episode_num),
    ]

    log(f"{log_prefix}  命令行: {cmd}")

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
        )
        # 记录脚本输出到日志
        if r.stdout:
            for line in r.stdout.strip().splitlines():
                log(f"{log_prefix}  [STDOUT] {line}", console=False)
        if r.returncode == 0:
            return True, f"OK ({r.returncode})"
        else:
            err = r.stderr[-500:] if r.stderr else "unknown error"
            return False, f"exit={r.returncode} | {err}"
    except subprocess.TimeoutExpired:
        return False, "timeout (>600s)"
    except Exception as e:
        return False, str(e)


def log_failure(dir_name, ep, msg):
    """立即记录失败的集数到文件（带时间戳）"""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(FAILED_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{dir_name}] 第{ep}集: {msg}\n")


def process_directory(directory, global_idx, total_videos, failure_log):
    """处理单个文件夹，返回 (success_count, fail_count, fail_list)"""
    dir_name = os.path.basename(directory)
    log(f"\n{'#'*60}")
    log(f"# 文件夹 [{dir_name}]")
    log(f"# 路径: {directory}")
    log(f"{'#'*60}")

    if not os.path.isdir(directory):
        log(f"[ERROR] 目录不存在，跳过: {directory}")
        return 0, 0, []

    # 获取已分析和待处理列表
    analyzed = get_already_analyzed(directory)
    all_videos = find_mp4_files(directory)

    todo = [(ep, fname, path) for ep, fname, path in all_videos if ep not in analyzed]

    log(f"  总视频数: {len(all_videos)}")
    log(f"  已分析: {len(analyzed)} 集 -> {sorted(analyzed) if analyzed else '无'}")
    log(f"  待处理: {len(todo)} 集")

    if not todo:
        log("  ✔ 全部已分析完成，跳过此文件夹。")
        return 0, 0, []

    success = 0
    fail = 0
    fail_list = []

    for i, (ep, fname, vpath) in enumerate(todo, 1):
        out_name = f"{ep}集_分镜脚本.txt"
        out_path = os.path.join(directory, out_name)
        prefix = f"  [{i}/{len(todo)}][全局{global_idx}/{total_videos}] 第{ep}集"

        # 检查输出是否已存在（防止并发重复）
        if os.path.exists(out_path):
            log(f"{prefix} ✔ 输出已存在，跳过")
            success += 1
            continue

        size_mb = os.path.getsize(vpath) / 1024 / 1024
        log(f"{prefix} 开始... ({size_mb:.1f} MB)")

        ok, msg = process_video(vpath, out_path, ep, log_prefix=f"  [{i}/{len(todo)}]")
        if ok and os.path.exists(out_path):
            sz = os.path.getsize(out_path)
            log(f"{prefix} ✔ 成功 ({sz} bytes)")
            success += 1
        else:
            log(f"{prefix} ✘ 失败: {msg}")
            fail += 1
            fail_list.append((dir_name, ep, msg))
            # 立即记录到失败日志文件
            log_failure(dir_name, ep, msg)

        # 每个视频之间稍微暂停，避免 API 限流
        if i < len(todo):
            time.sleep(2)

    return success, fail, fail_list


def main():
    log("=" * 60)
    log("批量视频分镜脚本分析器 v3")
    log("=" * 60)

    # 初始化失败日志文件
    with open(FAILED_LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + "="*60 + "\n")
        f.write(f"批量分析任务开始: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*60 + "\n")

    # 解析命令行参数中的目录列表
    dirs = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            dirs.append(arg)
        else:
            log(f"[WARN] 命令行参数不是有效目录，忽略: {arg}")

    if not dirs:
        dirs = VIDEO_DIRS
        log(f"使用脚本内预设目录（{len(dirs)} 个）")
    else:
        log(f"使用命令行指定的 {len(dirs)} 个目录")

    for d in dirs:
        log(f"  - {d}")

    # 预先统计总视频数
    total = 0
    for d in dirs:
        videos = find_mp4_files(d)
        analyzed = get_already_analyzed(d)
        todo_count = len([ep for ep, _, _ in videos if ep not in analyzed])
        total += todo_count
        log(f"  {os.path.basename(d)}: {len(videos)}视频, {len(analyzed)}已分析, {todo_count}待处理")

    log(f"\n总计待处理: {total} 个视频")
    log("-" * 60)

    all_success = 0
    all_fail = 0
    all_fail_list = []
    global_idx = 0

    for d in dirs:
        s, f, fl = process_directory(d, global_idx + 1, total, FAILED_LOG_FILE)
        all_success += s
        all_fail += f
        all_fail_list.extend(fl)
        global_idx += s + f

    log("\n" + "=" * 60)
    log("全部文件夹处理完成！")
    log(f"  成功: {all_success}")
    log(f"  失败: {all_fail}")
    if all_fail_list:
        log("  失败详情:")
        for dir_name, ep, msg in all_fail_list:
            log(f"    [{dir_name}] 第{ep}集: {msg[:80]}")
        # 写入失败日志文件摘要
        with open(FAILED_LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "="*60 + "\n")
            f.write(f"任务完成: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"成功: {all_success}, 失败: {all_fail}\n")
            if all_fail_list:
                f.write("失败详情:\n")
                for dir_name, ep, msg in all_fail_list:
                    f.write(f"  [{dir_name}] 第{ep}集: {msg[:100]}\n")
            f.write("="*60 + "\n")
    log("=" * 60)
    log(f"日志文件: {LOG_FILE}")
    log(f"失败记录: {FAILED_LOG_FILE}")


if __name__ == "__main__":
    main()
