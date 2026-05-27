import sys, json, base64, urllib.request, time, os, io
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_BASE = "https://grok.285my.cn/v1"
API_KEY = "sk-0Qr7FTfaeQEE1BnLeKNmtujWiT7YScjdgz4jjou5bTJ3H5W0"
IMAGE_PATH = r"E:\角色图\111现代人物\Gemini_Generated_Image_1qisic1qisic1qis.png"
DESKTOP = r"C:\Users\Administrator\Desktop"
PROMPT = "一个女人站在酒店的大堂微笑着说：欢迎光临"
MODEL = "seedance-2.0-480p-automatic-lingchuang"

# Read image
print("读取原图...")
with open(IMAGE_PATH, "rb") as f:
    raw = f.read()
print(f"原图大小: {len(raw)} bytes ({len(raw)/1024:.1f} KB)")

# Try to compress with PIL if available
try:
    from PIL import Image
    img = Image.open(io.BytesIO(raw))
    print(f"图片尺寸: {img.size}, 模式: {img.mode}")
    # Resize to max 1024 wide (480p video doesn't need huge input)
    if img.width > 1024:
        ratio = 1024 / img.width
        new_size = (1024, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        print(f"缩放至: {new_size}")
    # Save as JPEG with compression
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=75, optimize=True)
    img_bytes = buf.getvalue()
    print(f"压缩后: {len(img_bytes)} bytes ({len(img_bytes)/1024:.1f} KB)")
except ImportError:
    print("PIL 不可用，使用原图")
    img_bytes = raw

# Base64 encode
image_b64 = base64.b64encode(img_bytes).decode("utf-8")
print(f"Base64: {len(image_b64)} chars")

# Build payload
payload = json.dumps({
    "model": MODEL,
    "prompt": PROMPT,
    "image": image_b64,
    "seconds": "5"
}).encode("utf-8")
print(f"Payload: {len(payload)} bytes ({len(payload)/1024:.1f} KB)")

# Submit
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

    task_id = result.get("task_id")
    if task_id:
        print(f"\n轮询任务: {task_id}")
        for i in range(60):
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
                fail_reason = d.get("fail_reason", inner.get("error", str(data)[:500]))
                print(f"\n失败原因: {fail_reason}")
                break
        else:
            print("\n超时")
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")
    print(f"HTTP {e.code}: {body}")
