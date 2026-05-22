"""垫图生图 —— 调用豹剪 API 生成 16:9 欧式庄园场景图。
严格按照用户提供的多图垫图方案 + GPT Image 2 API 完整指南。
"""
import base64
import json
import re
import sys
import time
from pathlib import Path

import requests

# ── 配置 ─────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config" / "config.json"
cfg = json.loads(CONFIG_PATH.read_text("utf-8"))
api_cfg = cfg["Api"]

BASE_URL = "https://bj.nfai.lol/pg"
ENDPOINT = "/chat/completions"
SESSION_COOKIE = api_cfg["SessionCookie"]
MODEL = "gpt-image-2-2k"
SIZE = "1792x1024"
GROUP = "default"
DESKTOP = Path.home() / "Desktop"

raw_uid = api_cfg.get("UserId", "13679")
try:
    uid_obj = json.loads(raw_uid)
    USER_ID = str(uid_obj.get("id", 13679))
except (json.JSONDecodeError, TypeError):
    USER_ID = str(raw_uid)

REF1 = Path(r"E:\角色图\111现代人物\3a78bb994d73f9e8741ca0e9868fcfb1cb1fa08f1fa9c5-bfw1tS_fw658webp.jpg")
REF2 = Path(r"E:\角色图\111现代人物\c2d65296574f552d43f264ac5f5595fa1f8eb4675328c-g5O3oZ_fw658webp.jpg")

PROMPT = (
    "请严格参考两张图片中两个不同人物的外貌特征（发型、五官、气质、脸型），"
    "将两个人物都放入画面中，创作一张16:9的欧式庄园场景图。"
    "两个人物穿着优雅的欧式服饰，站在一座宏伟的古典欧式庄园前，"
    "背景有花园、喷泉、古典建筑，两人之间有自然互动，"
    "柔和自然光，电影级画质，精致的细节，油画质感。"
)


# ── 图片编码 ─────────────────────────────────────────────────

def encode_image(path: Path, max_dim: int = 1024) -> str:
    """编码图片为 base64 data URL，适度压缩减少代理断连风险。"""
    from PIL import Image
    import io

    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    size_kb = buf.tell() / 1024
    print(f"  {path.name}: {w}x{h} -> {img.size[0]}x{img.size[1]}, {size_kb:.0f}KB base64")
    return f"data:image/jpeg;base64,{b64}"


# ── API 调用 ─────────────────────────────────────────────────

def call_api(prompt: str, ref_paths: list[Path]) -> str | None:
    """调用豹剪 API 生成图片（按多图垫图方案 §4-§5）。"""
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"session={SESSION_COOKIE}",
        "new-api-user": USER_ID,
    }

    # 所有参考图放 content 前面，文本指令放最后
    content = []
    for p in ref_paths:
        content.append({
            "type": "image_url",
            "image_url": {"url": encode_image(p), "detail": "high"},
        })
    content.append({"type": "text", "text": prompt})

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "stream": True,
        "size": SIZE,
        "group": GROUP,
    }

    url = f"{BASE_URL}{ENDPOINT}"
    print(f"  Prompt: {prompt[:80]}...")
    print(f"  Payload: {len(json.dumps(payload, ensure_ascii=False)) / 1024:.0f}KB")

    for attempt in range(5):
        try:
            print(f"  Attempt {attempt + 1}/5...")
            resp = requests.post(url, headers=headers, json=payload, timeout=300, stream=True)
            print(f"  Status: {resp.status_code}, CT: {resp.headers.get('Content-Type', '')[:50]}")

            if resp.status_code != 200:
                print(f"  Body: {resp.text[:300]}")
                return None

            # SSE 流式解析
            content_parts = []
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if "error" in chunk:
                    err = chunk["error"]
                    msg = err.get("message", json.dumps(err, ensure_ascii=False))
                    print(f"  SSE error: {msg}")
                    return None

                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    err = delta.get("error")
                    if err:
                        print(f"  Model error: {err}")
                    text = delta.get("content", "")
                    if text:
                        content_parts.append(text)
                        print(text, end="", flush=True)

            full = "".join(content_parts)
            print(f"\n  Total: {len(full)} chars")

            if not full:
                print("  Empty response, retrying...")
                time.sleep(3)
                continue

            # GPT 格式提取 URL
            match = re.search(r"!\[.*?\]\((https?://\S+)\)", full)
            if match:
                return match.group(1)

            print(f"  No URL in: {full[:300]}")
            return None

        except (requests.exceptions.ProxyError,
                requests.exceptions.ConnectionError) as e:
            print(f"  Connection error: {type(e).__name__}, retry in {3 * (attempt + 1)}s...")
            time.sleep(3 * (attempt + 1))

    return None


def download(url: str, name: str) -> None:
    """下载图片到桌面。"""
    out = DESKTOP / name
    if url.startswith("data:"):
        _, b64 = url.split(",", 1)
        data = base64.b64decode(b64)
    else:
        data = requests.get(url, timeout=120).content
    out.write_bytes(data)
    print(f"  Saved: {out}  ({len(data):,} bytes)")


# ── 主流程 ────────────────────────────────────────────────────

def main() -> None:
    print(f"User ID: {USER_ID}, Model: {MODEL}, Size: {SIZE}\n")

    print("Generating with 2 reference images...")
    img_url = call_api(PROMPT, [REF1, REF2])
    if not img_url:
        print("Generation failed after all retries!")
        sys.exit(1)

    print(f"\nImage URL: {img_url[:120]}...")
    download(img_url, "欧式庄园场景图.png")


if __name__ == "__main__":
    main()
