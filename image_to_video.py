import sys, json, base64, urllib.request, time, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_BASE = "https://grok.285my.cn/v1"
API_KEY = "sk-0Qr7FTfaeQEE1BnLeKNmtujWiT7YScjdgz4jjou5bTJ3H5W0"
IMAGE_PATH = r"E:\角色图\111现代人物\Gemini_Generated_Image_1qisic1qisic1qis.png"
DESKTOP = r"C:\Users\Administrator\Desktop"
PROMPT = "一个女人站在酒店的大堂微笑着说：欢迎光临"

# Read and encode image
print("读取图片...")
with open(IMAGE_PATH, "rb") as f:
    image_data = base64.b64encode(f.read()).decode("utf-8")
print(f"图片大小: {len(image_data)} chars (base64)")

# Try phver-video-lingchuang (cheapest, worked)
payload = json.dumps({
    "model": "seedance-2.0-480p-automatic-lingchuang",
    "prompt": PROMPT,
    "image": image_data,
    "seconds": "5"
}).encode("utf-8")

print(f"请求大小: {len(payload)} bytes")
print("提交任务...")

req = urllib.request.Request(
    f"{API_BASE}/video/generations",
    data=payload,
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
)

try:
    resp = urllib.request.urlopen(req, timeout=120)
    result = json.loads(resp.read())
    print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")

    if "task_id" in result:
        task_id = result["task_id"]
        print(f"\n轮询任务: {task_id}")

        for i in range(30):
            time.sleep(10)
            req2 = urllib.request.Request(
                f"{API_BASE}/video/generations/{task_id}",
                headers={"Authorization": f"Bearer {API_KEY}"}
            )
            resp2 = urllib.request.urlopen(req2, timeout=30)
            data = json.loads(resp2.read())

            d = data.get("data", {})
            inner = d.get("data", d)
            status = inner.get("status", d.get("status", "unknown"))
            progress = inner.get("progress", d.get("progress", 0))
            video_url = inner.get("video_url", d.get("video_url"))

            print(f"[{(i+1)*10}s] 状态: {status}, 进度: {progress}%", end="")

            if video_url:
                print(f"\n视频URL: {video_url}")
                filename = f"seedance_img2vid_{task_id[-8:]}.mp4"
                filepath = os.path.join(DESKTOP, filename)
                print(f"下载到: {filepath}")
                urllib.request.urlretrieve(video_url, filepath)
                print(f"下载完成! 文件: {filepath}")
                break
            else:
                print()

            if status in ("failed", "error"):
                print(f"\n任务失败: {data}")
                break
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")
    print(f"HTTP {e.code}: {body}")
