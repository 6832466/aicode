"""下载剩余缺失的视频到桌面"""
import sys, os, ssl, time, shutil

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CURRENT_DIR, '..', 'eaglepy310', 'Lib', 'site-packages'))
sys.stdout.reconfigure(encoding='utf-8')

import requests
import urllib3
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
                    print(f"  {pct}% {spd/1e6:.1f}MB/s {downloaded/1e6:.1f}/{total/1e6:.1f}MB", flush=True)
                    last = now

    os.replace(tmp, path)
    return path

def safe_name(title, prefix=""):
    safe = "".join(c for c in title if c.isalnum() or c in ' ._-')[:60]
    if not safe:
        safe = prefix + str(abs(hash(title)) % 100000)
    return safe

# ── 抖音 ──
print("=" * 50, flush=True)
print("[1] 抖音", flush=True)
try:
    client = videodl.VideoClient(allowed_video_sources=[])
    infos = client.parsefromurl("https://v.douyin.com/SkCPSv3WlME/")
    if infos:
        info = infos[0]
        title = info.get('title', 'douyin')
        ext = info.get('ext', 'mp4')
        dl_url = info.get('download_url', '')
        headers = dict(info.get('default_download_headers', {}) or {})

        print(f"  {title}", flush=True)
        print(f"  {str(dl_url)[:120]}", flush=True)

        if not dl_url or 'err_msg' in info:
            print(f"  SKIP: no URL", flush=True)
        else:
            fname = f"douyin_{safe_name(title, 'douyin')}.{ext}"
            spath = os.path.join(DESKTOP, fname)
            print(f"  -> {fname}", flush=True)
            result = download_with_progress(dl_url, spath, headers)

            if os.path.exists(result):
                sz = os.path.getsize(result) / 1e6
                # Copy with readable name
                readable = os.path.join(DESKTOP, f"douyin_恋恋喜钱第一集.{ext}")
                shutil.copy2(result, readable)
                print(f"  OK: {sz:.1f}MB -> {readable}", flush=True)
except Exception as e:
    print(f"  FAIL: {e}", flush=True)

# ── YouTube ──
print("\n" + "=" * 50, flush=True)
print("[2] YouTube", flush=True)
try:
    infos = client.parsefromurl("https://www.youtube.com/watch?v=tfeCwDT-5m0")
    if infos:
        info = infos[0]
        title = info.get('title', 'youtube')
        ext = info.get('ext', 'mp4')
        dl_url = info.get('download_url', '')
        headers = dict(info.get('default_download_headers', {}) or {})

        print(f"  {title}", flush=True)
        print(f"  Source: {info.get('source', '?')}", flush=True)

        if not dl_url or 'err_msg' in info:
            print(f"  SKIP: no URL / error: {info.get('err_msg', '')}", flush=True)
        else:
            fname = f"youtube_{safe_name(title, 'youtube')}.{ext}"
            spath = os.path.join(DESKTOP, fname)
            print(f"  -> {fname}", flush=True)
            result = download_with_progress(dl_url, spath, headers)

            if os.path.exists(result):
                sz = os.path.getsize(result) / 1e6
                readable = os.path.join(DESKTOP, f"youtube_{safe_name(title, 'yt')}.{ext}")
                shutil.copy2(result, readable)
                print(f"  OK: {sz:.1f}MB -> {readable}", flush=True)
            else:
                print(f"  FAIL: file not found", flush=True)
except Exception as e:
    print(f"  FAIL: {e}", flush=True)

print("\nDone!", flush=True)
