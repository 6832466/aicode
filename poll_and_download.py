import sys, time, urllib.request, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_BASE = "https://grok.285my.cn/v1"
API_KEY = "sk-0Qr7FTfaeQEE1BnLeKNmtujWiT7YScjdgz4jjou5bTJ3H5W0"
TASK_ID = "task_wozTIlgkVHmKXqbFvi2RvXnyTbmpddb2"
DESKTOP = r"C:\Users\Administrator\Desktop"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

print(f"轮询任务: {TASK_ID}")
max_wait = 300  # 最多等5分钟
interval = 10   # 每10秒查一次
elapsed = 0

while elapsed < max_wait:
    time.sleep(interval)
    elapsed += interval

    req = urllib.request.Request(
        f"{API_BASE}/video/generations/{TASK_ID}",
        headers=headers
    )
    resp = urllib.request.urlopen(req, timeout=30)
    data = __import__('json').loads(resp.read())

    d = data.get("data", {})
    inner = d.get("data", d)
    status = inner.get("status", d.get("status", "unknown"))
    progress = inner.get("progress", d.get("progress", 0))
    video_url = inner.get("video_url", d.get("video_url"))

    print(f"[{elapsed}s] 状态: {status}, 进度: {progress}%", end="")

    if video_url:
        print(f"\n视频URL: {video_url}")
        filename = f"seedance_output_{TASK_ID[-8:]}.mp4"
        filepath = os.path.join(DESKTOP, filename)
        print(f"下载到: {filepath}")
        urllib.request.urlretrieve(video_url, filepath)
        print(f"下载完成! 文件: {filepath}")
        break
    else:
        print()

    if status in ("completed", "success", "succeeded"):
        print(f"\n任务状态为 {status} 但没有 video_url，完整响应: {data}")
        break
    elif status in ("failed", "error"):
        print(f"\n任务失败: {data}")
        break
else:
    print(f"\n超时，已等待 {max_wait}s")
