"""
RunwayML 结果下载器 - 自动下载视频并匹配提示词

用法:
  python runway_downloader.py
  python runway_downloader.py --session-id=641c0c56-c296-4a23-a6f5-4b45a7bfacd9
  python runway_downloader.py --dry-run   # 仅预览不下载
"""

import json
import sys
import time
import requests
from pathlib import Path

# ========== 配置 ==========
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
TEAM_ID = "57508622"
API_BASE = "https://api.runwayml.com/v1"

# Token (从浏览器 localStorage RW_USER_TOKEN 获取)
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NTc1MDg2MjIsImVtYWlsIjoieHE3ODE3MDgwOUBnbWFpbC5jb20iLCJleHAiOjE3ODA0MDI0MDkuMjA3LCJpYXQiOjE3Nzc4MTA0MDkuMjA3LCJzc28iOmZhbHNlfQ.WCOHIUEwohSlPWoiO6cOylyXM5bsdNblBs6A08AJ4dU"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "x-runway-workspace": TEAM_ID,
    "x-runway-source-application": "web",
    "User-Agent": "Mozilla/5.0",
}


def api_get(path):
    """调用 RunwayML API"""
    resp = requests.get(f"{API_BASE}{path}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def list_sessions(limit=20):
    """列出最近的 sessions"""
    data = api_get(f"/sessions?asTeamId={TEAM_ID}&limit={limit}")
    sessions = data.get("sessions", [])
    for s in sessions:
        print(f"  {s['id'][:8]}...  {s.get('name', 'N/A')[:50]}  assets={s.get('assetCount', 0)}")
    return sessions


def download_session(session_id, dry_run=False):
    """下载一个 session 的所有视频，匹配提示词"""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"Session: {session_id}")

    # 1. 获取所有 assets
    assets_data = api_get(f"/sessions/{session_id}/assets?asTeamId={TEAM_ID}&limit=500")
    assets = assets_data.get("assets", [])
    video_assets = [a for a in assets if a.get("url")]

    # 区分视频和图片
    videos = [a for a in video_assets if ".mp4" in a.get("url", "")]
    images = [a for a in video_assets if ".jpg" in a.get("url", "") or ".png" in a.get("url", "")]
    print(f"视频: {len(videos)}  图片: {len(images)}")

    # 2. 构建 taskId -> prompt 映射
    task_prompt_map = {}
    task_cache = {}

    session_data = api_get(f"/sessions/{session_id}?asTeamId={TEAM_ID}")
    generations = session_data.get("generations", [])
    for gen in generations:
        tid = gen.get("taskId")
        if tid:
            task_cache[tid] = gen

    # 3. 处理每个视频
    results = []
    for i, asset in enumerate(videos):
        task_id = asset.get("taskId", "")
        video_url = asset.get("url", "")

        # 获取任务详情
        prompt = ""
        task_name = ""
        if task_id and task_id not in task_prompt_map:
            try:
                task_data = api_get(f"/tasks/{task_id}?asTeamId={TEAM_ID}")
                task = task_data.get("task", {})
                prompt = task.get("options", {}).get("textPrompt", "")
                task_name = task.get("name", "")
                task_prompt_map[task_id] = prompt
            except Exception:
                prompt = task_prompt_map.get(task_id, f"task_{task_id[:8]}")

        prompt = task_prompt_map.get(task_id, prompt)

        # 用任务名前缀 + 索引生成文件名
        safe_name = f"{i+1:03d}_{prompt[:60]}"
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in " _-，。、（）()").strip()
        filename = f"{safe_name}.mp4"

        filepath = DOWNLOAD_DIR / filename
        size_mb = 0

        if not dry_run:
            try:
                print(f"  [{i+1}] 下载: {prompt[:50]}...")
                r = requests.get(video_url, timeout=120, stream=True)
                r.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_mb = filepath.stat().st_size / (1024 * 1024)
                print(f"       [OK] {filename[:60]}... ({size_mb:.1f} MB)")
            except Exception as e:
                print(f"       [FAIL] {e}")
        else:
            print(f"  [{i+1}] [DRY-RUN] {prompt[:50]}... → {filename[:60]}...")

        results.append({
            "index": i + 1,
            "taskId": task_id,
            "prompt": prompt,
            "filename": filename,
            "size_mb": round(size_mb, 1),
        })

    # 4. 保存匹配清单
    if results:
        manifest = {
            "sessionId": session_id,
            "downloadedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "count": len(results),
            "results": results,
        }
        manifest_path = DOWNLOAD_DIR / f"manifest_{session_id[:8]}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n匹配清单: {manifest_path}")
        print(f"视频总数: {len(results)}")

    return results


def main():
    args = sys.argv[1:]
    session_id = None
    dry_run = "--dry-run" in args

    for a in args:
        if a.startswith("--session-id="):
            session_id = a.split("=", 1)[1]

    if not session_id:
        print("可用的 Sessions:")
        sessions = list_sessions()
        if sessions:
            session_id = sessions[0]["id"]
            print(f"\n使用最近的 session: {session_id}")
        else:
            print("没有找到 session")
            return

    download_session(session_id, dry_run=dry_run)
    print("\n完成！")


if __name__ == "__main__":
    main()
