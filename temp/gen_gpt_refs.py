"""Generate 16:9 image via GPT Image 2 with 3 reference images."""
import sys, os, time, json, io, base64, re
sys.path.insert(0, r"E:\AiCode\005flow2api")
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PySide6.QtWidgets import QApplication, QDialog
from cookie_util import CookieLoginDialog
import requests

PRESET_URL = "https://bj.nfai.lol/pg"
PRESET_PATH = "/chat/completions"
DESKTOP = os.path.join(os.environ["USERPROFILE"], "Desktop")

REF_IMAGES = [
    r"E:\角色图\111现代人物\3a78bb994d73f9e8741ca0e9868fcfb1cb1fa08f1fa9c5-bfw1tS_fw658webp.jpg",
    r"E:\角色图\111现代人物\32eafaed8dbad87691735842b761b95055a5734d50110-U7y9wj_fw658webp.jpg",
    r"E:\角色图\111现代人物\62d885285d50f1ccf7555e8acec3c29ae0ece32d3e66d-4cvVVn_fw658webp.jpg",
]

PROMPT = """请参考这三张图片中的人物外貌和特征，创作一张 16:9 横屏图片。

要求：
- 保持三个人的面部特征、发型、五官不变
- 给他们设计一个好看的现代都市背景（咖啡厅、书店、或城市街景）
- 16:9 宽屏比例
- 光线柔和，画面高质量，构图美观
- 自然的互动姿态"""

# Step 1: Login
print("Opening login dialog...")
app = QApplication(sys.argv)
login = CookieLoginDialog()
if login.exec() != QDialog.Accepted:
    print("Login cancelled.")
    sys.exit(0)
cookie = login.session_cookie
uid = login.user_id
print(f"Got cookie ({len(cookie)} chars), uid={uid}")

headers = {
    "Content-Type": "application/json",
    "Cookie": f"session={cookie}",
    "new-api-user": uid,
}

# Step 2: Load and encode reference images
print("\nLoading reference images...")
ref_parts = []
for i, path in enumerate(REF_IMAGES):
    with open(path, "rb") as f:
        data = f.read()
    mime = "image/webp" if path.endswith(".webp") else "image/jpeg"
    b64 = base64.b64encode(data).decode("utf-8")
    data_uri = f"data:{mime};base64,{b64}"
    ref_parts.append({
        "type": "image_url",
        "image_url": {"url": data_uri, "detail": "high"},
    })
    print(f"  [{i+1}] {os.path.basename(path)}: {len(data):,} bytes → {len(data_uri):,} chars b64")

# Step 3: Build request payload
content = ref_parts + [
    {"type": "text", "text": PROMPT},
]
payload = {
    "model": "gpt-image-2",
    "messages": [{"role": "user", "content": content}],
    "stream": True,
    "size": "1792x1024",
    "group": "default",
}

print(f"\nPayload size: {len(json.dumps(payload)):,} bytes")
print(f"Model: gpt-image-2, Size: 1792x1024 (16:9)")

# Step 4: Send request
print(f"\nSending to {PRESET_URL}{PRESET_PATH}...")
resp = requests.post(
    f"{PRESET_URL}{PRESET_PATH}",
    headers=headers,
    json=payload,
    timeout=300,
    stream=True,
)

print(f"HTTP {resp.status_code}")

if resp.status_code != 200:
    print(f"Error: {resp.text[:500]}")
    sys.exit(1)

# Step 5: Read SSE stream
print("Reading response stream...")
content_parts = []
for line in resp.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    data_str = line[6:].strip()
    if data_str == "[DONE]":
        break
    try:
        data = json.loads(data_str)
        if "error" in data:
            print(f"SSE error: {data['error']}")
            break
        for c in data.get("choices", []):
            delta = c.get("delta", {})
            if delta.get("content"):
                content_parts.append(delta["content"])
    except Exception:
        pass

full_content = "".join(content_parts)
print(f"Response: {len(full_content):,} chars")

# Step 6: Extract and download image
from utils import extract_image_url_from_content
image_url = extract_image_url_from_content(full_content)

if not image_url and "data:image" in full_content:
    # Manual extraction for base64 embedded images
    m = re.search(r'!\[.*?\]\((data:image/[^)]+)\)', full_content)
    if m:
        image_url = m.group(1)
        print(f"Manual extract: {image_url[:100]}...")

if not image_url:
    print("No image URL found! Content preview:")
    print(full_content[:500])
    sys.exit(1)

print(f"Image URL: {image_url[:150]}...")

# Download
if image_url.startswith("data:image/png;base64,") or image_url.startswith("data:image/jpeg;base64,"):
    b64_data = image_url.split(",", 1)[1]
    img_data = base64.b64decode(b64_data)
elif image_url.startswith("data:"):
    b64_data = image_url.split(",", 1)[1]
    img_data = base64.b64decode(b64_data)
else:
    img_resp = requests.get(image_url, timeout=120)
    img_data = img_resp.content

print(f"Downloaded: {len(img_data):,} bytes ({len(img_data)/1024/1024:.2f} MB)")

# Measure dimensions
from PIL import Image
img = Image.open(io.BytesIO(img_data))
print(f"Dimensions: {img.size[0]}x{img.size[1]} — {'16:9 ✓' if abs(img.size[0]/img.size[1] - 16/9) < 0.05 else f'{img.size[0]/img.size[1]:.2f}:1'}")

# Save
out = os.path.join(DESKTOP, "gpt_3refs_16x9.png")
with open(out, "wb") as f:
    f.write(img_data)
print(f"\n✅ Saved: {out}")
