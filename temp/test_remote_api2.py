"""Round 2: download images properly & measure dimensions."""
import sys, json, os, io, re
sys.path.insert(0, r"E:\AiCode\005flow2api")
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from PIL import Image
from utils import extract_image_url_from_content

PRESET_URL = "https://bj.nfai.lol/pg"
PRESET_PATH = "/chat/completions"

# Read cookie from first test (user already logged in)
from config import cfg
cookie = cfg.api_session_cookie.value

if not cookie:
    # Login again
    from PySide6.QtWidgets import QApplication, QDialog
    from cookie_util import CookieLoginDialog
    app = QApplication(sys.argv)
    login = CookieLoginDialog()
    if login.exec() != QDialog.Accepted:
        print("Login cancelled.")
        sys.exit(0)
    cookie = login.session_cookie
    uid = login.user_id
else:
    uid = cfg.user_id.value or "13679"

headers = {
    "Content-Type": "application/json",
    "Cookie": f"session={cookie}",
    "new-api-user": uid,
}

test_cases = [
    ("gpt-image-2", "1024x1024", "GPT Image 2 — 方形"),
    ("gpt-image-2", "1792x1024", "GPT Image 2 — 横屏"),
    ("gpt-image-2", "", "GPT Image 2 — 无size参数"),
    ("gpt-image-2-2k", "1792x1024", "GPT Image 2-2K — 横屏"),
    ("gpt-image-2-4k", "1792x1024", "GPT Image 2-4K — 横屏"),
]

desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")

for model, size, label in test_cases:
    print(f"\n{'='*50}")
    print(f"{label} | model={model}, size={size or '(none)'}")
    print(f"{'='*50}")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "画一只可爱的卡通猫，纯色背景"}],
        "stream": True,
        "group": "default",
    }
    if size:
        payload["size"] = size

    try:
        resp = requests.post(
            f"{PRESET_URL}{PRESET_PATH}",
            headers=headers, json=payload, timeout=120, stream=True,
        )
        if resp.status_code != 200:
            print(f"HTTP {resp.status_code}: {resp.text[:300]}")
            continue

        # Collect full content and extract image URL using the real function
        content_parts = []
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                for c in data.get("choices", []):
                    delta = c.get("delta", {})
                    if delta.get("content"):
                        content_parts.append(delta["content"])
            except Exception:
                pass

        full_content = "".join(content_parts)
        print(f"Response: {len(full_content):,} chars")

        image_url = extract_image_url_from_content(full_content)
        if image_url:
            print(f"URL: {image_url[:150]}…")

            # Download the image
            if image_url.startswith("data:image/png;base64,"):
                # Base64 embedded PNG
                import base64
                b64_data = image_url.split(",", 1)[1]
                img_data = base64.b64decode(b64_data)
            elif image_url.startswith("data:"):
                import base64
                b64_data = image_url.split(",", 1)[1]
                img_data = base64.b64decode(b64_data)
            else:
                img_resp = requests.get(image_url, timeout=60)
                img_data = img_resp.content

            print(f"Downloaded: {len(img_data):,} bytes ({len(img_data)/1024:.1f} KB)")

            # Measure dimensions
            img = Image.open(io.BytesIO(img_data))
            print(f"Dimensions: {img.size[0]}x{img.size[1]} ({img.mode})")

            # Save sample
            safe_name = label.replace(" ", "_").replace("—", "-").replace("/", "_")
            fname = os.path.join(desktop, f"api_test_{safe_name}.png")
            with open(fname, "wb") as f:
                f.write(img_data)
            print(f"Saved: {fname}")
        else:
            print("No image URL extracted!")
            # Check for data:image in raw content
            if "data:image" in full_content:
                print("Content contains data:image — extract function may need update")
                # Try manual extraction
                match = re.search(r'!\[.*?\]\((data:image/[^;]+;base64,[^)]+)\)', full_content)
                if match:
                    print(f"Manual regex found match: {match.group(0)[:200]}")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

print("\nDone.")
