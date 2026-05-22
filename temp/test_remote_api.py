"""Test remote API — login → test GPT image + size params."""
import sys, json, os
sys.path.insert(0, r"E:\AiCode\005flow2api")
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit, QPushButton
from cookie_util import CookieLoginDialog
import requests

PRESET_URL = "https://bj.nfai.lol/pg"
PRESET_PATH = "/chat/completions"

app = QApplication(sys.argv)

# --- Step 1: Login ---
print("Opening login dialog...")
login = CookieLoginDialog()
if login.exec() != QDialog.Accepted:
    print("Login cancelled.")
    sys.exit(0)

cookie = login.session_cookie
uid = login.user_id
print(f"Got cookie: {'*' * min(len(cookie), 10)}… ({len(cookie)} chars)")
print(f"User ID: {uid}")

# --- Step 2: Verify connection ---
print("\n" + "=" * 50)
print("Checking API connection…")
headers = {
    "Content-Type": "application/json",
    "Cookie": f"session={cookie}",
    "new-api-user": uid,
}

# Check /api/status (root level)
try:
    r = requests.get("https://bj.nfai.lol/api/status", headers=headers, timeout=10)
    print(f"Status endpoint: HTTP {r.status_code}")
    if r.status_code == 200:
        print(f"  {r.json()}")
except Exception as e:
    print(f"Status check failed: {e}")

# --- Step 3: Test GPT models with size ---
print("\n" + "=" * 50)
print("Testing GPT image generation with size params")
print("=" * 50)

test_cases = [
    # (model, size, label)
    ("gpt-image-2", "1024x1024", "GPT Image 2 — 方形 1K"),
    ("gpt-image-2-2k", "1792x1024", "GPT Image 2-2K — 横屏 2K"),
    ("gpt-image-2-4k", "1792x1024", "GPT Image 2-4K — 横屏"),
    ("gemini-2.5-flash-image", "1024x1024", "Gemini 2.5 Flash — 方形 (对照)"),
]

for model, size, label in test_cases:
    print(f"\n--- {label} ---")
    print(f"Model: {model}, Size: {size}")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "画一只可爱的卡通猫，纯色背景"}],
        "stream": True,
        "size": size,
        "group": "default",
    }

    print(f"Request payload: {json.dumps(payload, ensure_ascii=False)}")

    try:
        resp = requests.post(
            f"{PRESET_URL}{PRESET_PATH}",
            headers=headers,
            json=payload,
            timeout=120,
            stream=True,
        )
        print(f"HTTP {resp.status_code}")
        content_type = resp.headers.get("Content-Type", "")
        print(f"Content-Type: {content_type}")

        if resp.status_code != 200:
            body = resp.text[:500]
            print(f"Error body: {body}")
            continue

        if "text/event-stream" in content_type:
            # Read SSE stream
            lines = []
            image_url = None
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        for c in choices:
                            delta = c.get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                lines.append(content)
                                # Check for image URL in content
                                import re
                                urls = re.findall(r'https?://[^\s"\'<>\]]+', content)
                                if urls:
                                    image_url = urls[-1]
                    except Exception:
                        pass

            full_content = "".join(lines)
            print(f"Stream content length: {len(full_content)} chars")
            if image_url:
                print(f"Image URL: {image_url[:200]}…")
                # Download preview
                try:
                    img_resp = requests.get(image_url, timeout=30)
                    print(f"  Image size: {len(img_resp.content):,} bytes ({len(img_resp.content)/1024:.1f} KB)")
                except Exception as e:
                    print(f"  Image download failed: {e}")
            else:
                print(f"  No image URL in response!")
                print(f"  Content preview: {full_content[:300]}")
        else:
            # Non-streaming response
            body = resp.text[:800]
            print(f"Response: {body}")

    except requests.exceptions.Timeout:
        print("TIMEOUT")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

print("\n" + "=" * 50)
print("Test complete.")
