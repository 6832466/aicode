"""Download all 4 videos to desktop with readable filenames"""
import sys, os, ssl, time, re, json

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CURRENT_DIR, '..', 'eaglepy310', 'Lib', 'site-packages'))
sys.stdout.reconfigure(encoding='utf-8')

import requests, urllib3
urllib3.disable_warnings()

from videodl import videodl

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

class AnyCipher(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *a, **kw):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers('DEFAULT:@SECLEVEL=0')
        kw['ssl_context'] = ctx
        return super().init_poolmanager(*a, **kw)

def safe_name(title, prefix=""):
    safe = "".join(c for c in title if c.isalnum() or c in ' ._-')[:60]
    if not safe:
        safe = prefix + str(abs(hash(title)) % 100000)
    return safe.strip()

def download_with_progress(url, path, headers=None):
    s = requests.Session()
    s.mount('https://', AnyCipher())
    hdrs = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'}
    if headers:
        hdrs.update(headers)

    resp = None
    last_err = None
    for proto_url in [url, url.replace('https://', 'http://')]:
        try:
            resp = s.get(proto_url, headers=hdrs, stream=True, timeout=(30, 120), verify=False)
            resp.raise_for_status()
            break
        except Exception as e:
            last_err = e
    if resp is None:
        raise last_err

    total = int(resp.headers.get('Content-Length', 0))
    downloaded = 0
    start = time.time()
    last = start
    tmp = path + '.part'

    with open(tmp, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if now - last >= 1:
                    pct = int(downloaded / total * 100) if total > 0 else 0
                    spd = downloaded / max(now - start, 0.001)
                    spd_s = f"{spd/1e6:.1f}MB/s" if spd > 1e6 else f"{spd/1e3:.0f}KB/s"
                    sz = f"{total/1e6:.1f}MB" if total else "?"
                    print(f"  {pct}% {spd_s} {downloaded/1e6:.1f}/{sz}", flush=True)
                    last = now

    os.replace(tmp, path)
    return path

# ── Kuaishou (manual, avoid DrissionPage hang) ──
def parse_kuaishou(url):
    """Manual kuaishou parser using requests only (skips DrissionPage)"""
    from bs4 import BeautifulSoup
    import json_repair
    from urllib.parse import urlparse

    s = requests.Session()
    s.mount('https://', AnyCipher())
    hdrs = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
        'Referer': 'https://v.kuaishou.com/'
    }

    resp = s.get(url, headers=hdrs, timeout=30, verify=False)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    soup = BeautifulSoup(resp.text, 'lxml')

    # Extract __APOLLO_STATE__
    apollo_match = re.search(r'window\.__APOLLO_STATE__\s*=\s*(\{.*?\});', str(soup), re.S)
    if not apollo_match:
        raise RuntimeError("Cannot find __APOLLO_STATE__ in kuaishou page")

    raw_data = json_repair.loads(apollo_match.group(1))
    client = raw_data["defaultClient"]

    # Find the photo key
    photo_key = next((k for k, v in client.items() if isinstance(v, dict) and v.get("__typename") == "VisionVideoDetailPhoto"), "")
    if not photo_key:
        raise RuntimeError("Cannot find VisionVideoDetailPhoto in APOLLO_STATE")

    photo = client[photo_key]
    title = photo.get('caption', 'kuaishou')

    # Collect candidates
    candidates = []
    if photo.get("photoH265Url"):
        candidates.append({"codec": "hevc_single", "maxBitrate": 1, "resolution": 1, "url": photo["photoH265Url"]})
    if photo.get("photoUrl"):
        candidates.append({"codec": "h264_single", "maxBitrate": 1, "resolution": 1, "url": photo["photoUrl"]})
    vr = photo.get("videoResource", {}) or {}
    j = vr.get("json", {}) or {}
    for codec in ("hevc", "h264"):
        for a in j.get(codec, {}).get("adaptationSet", []):
            for r in a.get("representation", []):
                if r.get("url"):
                    candidates.append({
                        "codec": codec,
                        "maxBitrate": r.get("maxBitrate", 0),
                        "resolution": r.get("width", 0) * r.get("height", 0),
                        "url": r.get("url"),
                    })

    codec_priority = {"hevc": 2, "hevc_single": 2, "h264": 1, "h264_single": 1}
    candidates = [c for c in candidates if c.get('url')]
    candidates.sort(key=lambda c: (codec_priority.get(c["codec"], 0), c["maxBitrate"], c["resolution"]), reverse=True)

    if not candidates:
        raise RuntimeError("No video candidates found")

    dl_url = candidates[0]["url"]
    return title, dl_url, "mp4"

print("=" * 50, flush=True)
print("[kuaishou] https://v.kuaishou.com/Kdt9wi7I", flush=True)
try:
    title, dl_url, ext = parse_kuaishou("https://v.kuaishou.com/Kdt9wi7I")
    print(f"  Title: {title}", flush=True)
    print(f"  URL: {str(dl_url)[:120]}", flush=True)
    fname = f"kuaishou_{safe_name(title, 'kuaishou')}.{ext}"
    spath = os.path.join(DESKTOP, fname)
    print(f"  -> {fname}", flush=True)
    result = download_with_progress(dl_url, spath)
    if os.path.exists(result):
        sz = os.path.getsize(result) / 1e6
        print(f"  OK: {sz:.1f}MB -> {fname}", flush=True)
except Exception as e:
    print(f"  FAIL: {e}", flush=True)
    import traceback
    traceback.print_exc()

# ── Douyin, Bilibili, YouTube (via videodl) ──
REMAINING = [
    ("https://v.douyin.com/SkCPSv3WlME/", "douyin"),
    ("https://www.bilibili.com/video/BV1He23BQErf/", "bilibili"),
    ("https://www.youtube.com/watch?v=tfeCwDT-5m0", "youtube"),
]

# Only use specific clients to avoid kuaishou DrissionPage
client = videodl.VideoClient(allowed_video_sources=[
    'DouyinVideoClient',
    'BilibiliVideoClient',
    'YouTubeVideoClient',
])

for url, prefix in REMAINING:
    print(f"\n{'='*50}", flush=True)
    print(f"[{prefix}] {url[:80]}", flush=True)

    try:
        infos = client.parsefromurl(url)
        if not infos:
            print(f"  SKIP: no parse result", flush=True)
            continue

        info = infos[0]
        err = info.get('err_msg', '')
        if err:
            print(f"  SKIP: {err[:150]}", flush=True)
            continue

        title = info.get('title', prefix)
        ext = info.get('ext', 'mp4')
        dl_url = info.get('download_url', '')
        headers = dict(info.get('default_download_headers', {}) or {})

        print(f"  Title: {title}", flush=True)
        print(f"  Source: {info.get('source', '?')}", flush=True)
        print(f"  URL: {str(dl_url)[:120]}", flush=True)

        if not dl_url:
            print(f"  SKIP: no download URL", flush=True)
            continue

        fname = f"{prefix}_{safe_name(title, prefix)}.{ext}"
        spath = os.path.join(DESKTOP, fname)
        print(f"  -> {fname}", flush=True)

        result = download_with_progress(dl_url, spath, headers)

        if os.path.exists(result):
            sz = os.path.getsize(result) / 1e6
            print(f"  OK: {sz:.1f}MB -> {fname}", flush=True)
        else:
            print(f"  FAIL: file not found after download", flush=True)

    except Exception as e:
        print(f"  FAIL: {e}", flush=True)
        import traceback
        traceback.print_exc()

print(f"\n{'='*50}", flush=True)
print("Desktop results:", flush=True)
for prefix in ['douyin', 'kuaishou', 'bilibili', 'youtube']:
    for f in os.listdir(DESKTOP):
        if f.lower().startswith(prefix) and f.lower().endswith(('.mp4', '.mkv', '.webm', '.flv')):
            sz = os.path.getsize(os.path.join(DESKTOP, f)) / 1e6
            print(f"  {f} ({sz:.1f}MB)", flush=True)
            break

print("\nDone!", flush=True)
