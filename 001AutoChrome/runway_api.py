"""
RunwayML API 批量视频生成脚本

用法:
  python runway_api.py                  # 运行所有待处理任务
  python runway_api.py --dry-run        # 预览模式
  python runway_api.py --start=5        # 从第5条开始
  python runway_api.py --check          # 查看当前任务状态
  python runway_api.py --download       # 下载已完成的任务视频
"""

import json
import sys
import time
import uuid
import requests
from pathlib import Path

# ========== 配置 ==========
BASE = Path(__file__).parent
PROMPTS_FILE = BASE / "prompts.json"
CHAR_ASSETS_FILE = BASE / "character_assets.json"
DOWNLOAD_DIR = BASE / "downloads"
LOG_FILE = BASE / "api_batch_log.json"

TEAM_ID = "57508622"
API_BASE = "https://api.runwayml.com/v1"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NTc1MDg2MjIsImVtYWlsIjoieHE3ODE3MDgwOUBnbWFpbC5jb20iLCJleHAiOjE3ODA0MDI0MDkuMjA3LCJpYXQiOjE3Nzc4MTA0MDkuMjA3LCJzc28iOmZhbHNlfQ.WCOHIUEwohSlPWoiO6cOylyXM5bsdNblBs6A08AJ4dU"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "x-runway-workspace": TEAM_ID,
    "x-runway-source-application": "web",
}

QUEUE_LIMIT = 2       # RunwayML 同时最多 2 个任务
POLL_INTERVAL = 10    # 轮询间隔秒
MAX_WAIT = 600        # 最大等待秒 (10分钟)


# ========== API 函数 ==========
def api_get(path):
    resp = requests.get(f"{API_BASE}{path}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_post(path, body):
    resp = requests.post(f"{API_BASE}{path}", headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def load_character_assets():
    """加载人物 → assetId 映射"""
    if CHAR_ASSETS_FILE.exists():
        return json.loads(CHAR_ASSETS_FILE.read_text(encoding="utf-8"))
    return {}


def save_character_assets(mapping):
    CHAR_ASSETS_FILE.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")


def load_log():
    """加载运行日志"""
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    return {"completed": [], "failed": [], "taskIds": [], "lastIndex": 0}


def save_log(log_data):
    LOG_FILE.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_active_tasks():
    """获取当前 session 中运行中的任务数"""
    try:
        data = api_get(f"/sessions?asTeamId={TEAM_ID}&limit=1")
        sessions = data.get("sessions", [])
        if not sessions:
            return 0
        sid = sessions[0]["id"]
        session_data = api_get(f"/sessions/{sid}?asTeamId={TEAM_ID}")
        generations = session_data.get("generations", [])
        running = sum(1 for g in generations if g.get("status") in ("PENDING", "PROCESSING", "THROTTLED"))
        return running
    except Exception as e:
        print(f"  [WARN] 获取任务状态失败: {e}")
        return 0


def wait_for_slot(max_wait=MAX_WAIT):
    """等待任务队列有空位"""
    waited = 0
    while waited < max_wait:
        active = get_active_tasks()
        if active < QUEUE_LIMIT:
            return True
        print(f"  队列已满 ({active}/{QUEUE_LIMIT})，等待 {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    return False


def create_generation(prompt_item, char_assets):
    """通过 API 创建视频生成任务"""
    references = prompt_item.get("references", [])
    prompt_text = prompt_item.get("prompt", "")
    duration = prompt_item.get("duration", 10)
    ratio = prompt_item.get("ratio", "16:9")
    source_row = prompt_item.get("_source_row", "?")

    # 构建 referenceImages
    reference_images = []
    for ref_name in references:
        if ref_name in char_assets:
            reference_images.append(char_assets[ref_name])
        else:
            print(f"  [WARN] 找不到人物 '{ref_name}' 的 assetId，跳过")

    if not reference_images and references:
        print(f"  [ERROR] 没有可用的 referenceImages")
        return None

    # 生成 taskId 和 name
    task_id = str(uuid.uuid4())
    ref_names = "_".join(references) if references else "no_ref"
    name = f"Seedance 2_0 - {ref_names}_{prompt_text[:20]}"

    body = {
        "toolId": "generate",
        "prompt": "",
        "outputs": {"outputUrls": []},
        "settings": {
            "duration": duration,
            "generateAudio": True,
            "exploreMode": True,
            "recordingEnabled": True,
            "name": name,
            "textPrompt": prompt_text,
            "referenceVideos": [],
            "referenceAudio": [],
            "resolution": "720p",
            "aspectRatio": ratio,
            "creationSource": "tool-mode",
            "taskId": task_id,
            "referenceImages": reference_images,
        },
    }

    try:
        result = api_post("/generations", body)
        gen_id = result.get("id", "?")
        print(f"  [OK] 创建成功: {gen_id} | refs={references} | dur={duration}s | ratio={ratio}")
        return {"id": gen_id, "taskId": task_id}
    except Exception as e:
        print(f"  [FAIL] API 错误: {e}")
        return None


def download_task_videos(task_id, prompt_text=""):
    """下载已完成任务的视频"""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        task_data = api_get(f"/tasks/{task_id}?asTeamId={TEAM_ID}")
        task = task_data.get("task", {})
        artifacts = task.get("artifacts", [])
        videos = [a for a in artifacts if a.get("url", "").endswith(".mp4")]

        results = []
        for i, video in enumerate(videos):
            safe_name = f"{prompt_text[:60]}_{i+1}"
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in " _-，。、（）()").strip()
            filename = f"{safe_name}.mp4"
            filepath = DOWNLOAD_DIR / filename

            r = requests.get(video["url"], timeout=120, stream=True)
            r.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"    下载: {filename[:60]}... ({size_mb:.1f} MB)")
            results.append({"filename": filename, "size_mb": round(size_mb, 1)})

        return results
    except Exception as e:
        print(f"    下载失败: {e}")
        return []


# ========== 主程序 ==========
def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    check_only = "--check" in args
    download_only = "--download" in args
    start_index = 0

    for a in args:
        if a.startswith("--start="):
            start_index = int(a.split("=")[1])

    # 加载配置
    if not PROMPTS_FILE.exists():
        print(f"[ERROR] 找不到: {PROMPTS_FILE}")
        sys.exit(1)

    prompts = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
    char_assets = load_character_assets()

    if not char_assets:
        print("[ERROR] 找不到 character_assets.json")
        print("请先创建人物映射文件，格式示例:")
        print(json.dumps({
            "xixi": {
                "assetId": "c22d4059-7927-48ac-839d-ba2b47d60f65",
                "url": "https://d2jqrm6oza8nb6.cloudfront.net/datasets/xxx.jpg?_jwt=..."
            },
            "duoduo": {
                "assetId": "6e54466d-b2ca-486a-81a3-2614746a2c59",
                "url": "https://d2jqrm6oza8nb6.cloudfront.net/datasets/xxx.jpg?_jwt=..."
            }
        }, indent=2, ensure_ascii=False))
        print("\n提示: 运行 python runway_api.py --extract-assets 来从浏览器提取")
        print("或者在 Chrome DevTools Network 面板中查看 POST /v1/generations 请求体")
        sys.exit(1)

    print(f"加载: {len(prompts)} 条提示词 | {len(char_assets)} 个人物映射 | start={start_index}")

    # --check
    if check_only:
        active = get_active_tasks()
        print(f"当前活跃任务: {active}/{QUEUE_LIMIT}")
        log = load_log()
        print(f"已完成: {len(log.get('completed', []))} | 失败: {len(log.get('failed', []))}")
        return

    # --download
    if download_only:
        log = load_log()
        for task in log.get("completed", []):
            tid = task.get("taskId", "")
            prompt = task.get("prompt", "")
            if tid:
                print(f"下载: {prompt[:50]}...")
                download_task_videos(tid, prompt)
        return

    # 检查人物映射是否覆盖所有需要的引用
    all_refs = set()
    for p in prompts:
        for r in p.get("references", []):
            all_refs.add(r)
    missing = all_refs - set(char_assets.keys())
    if missing:
        print(f"\n[WARN] 以下人物缺少 assetId 映射: {missing}")
        print("请在 character_assets.json 中添加对应条目后重试")
        if not dry_run:
            sys.exit(1)

    # 批量处理
    remaining = prompts[start_index:]
    print(f"\n处理 {len(remaining)} 个任务 | 队列限制: {QUEUE_LIMIT} | dry_run={dry_run}")

    if not dry_run:
        print("\n*** 3 秒后开始，Ctrl+C 取消 ***")
        for i in range(3, 0, -1):
            print(f"  {i}...")
            time.sleep(1)

    log = load_log()
    success_count = 0
    fail_count = 0

    for i, item in enumerate(remaining):
        idx = start_index + i
        refs = item.get("references", [])
        prompt = item.get("prompt", "")
        print(f"\n--- #{idx+1}/{len(prompts)} [{', '.join(refs)}] {prompt[:50]}... ---")

        if dry_run:
            print(f"  [DRY-RUN] dur={item.get('duration')}s ratio={item.get('ratio')}")
            continue

        # 等待队列有空位
        if not wait_for_slot():
            print("  [ERROR] 等待超时，终止运行")
            break

        # 创建任务
        result = create_generation(item, char_assets)
        if result:
            success_count += 1
            log["completed"].append({
                "index": idx,
                "references": refs,
                "prompt": prompt[:100],
                "genId": result["id"],
                "taskId": result["taskId"],
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
        else:
            fail_count += 1
            log["failed"].append({
                "index": idx,
                "references": refs,
                "prompt": prompt[:100],
                "error": "API creation failed",
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })

        log["lastIndex"] = idx
        save_log(log)

        print(f"进度: {i+1}/{len(remaining)} | OK:{success_count} FAIL:{fail_count}")

        # 任务间隔
        if i < len(remaining) - 1:
            time.sleep(3)

    print(f"\n===== 完成: OK={success_count} FAIL={fail_count} =====")
    print(f"日志已保存: {LOG_FILE}")

    # 提示下载
    if success_count > 0:
        print("\n生成完成后，运行以下命令下载视频:")
        print(f"  python {Path(__file__).name} --download")


if __name__ == "__main__":
    main()
