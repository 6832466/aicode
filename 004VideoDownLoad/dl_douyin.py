"""单独下载抖音视频到桌面"""
import sys, os, ssl
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CURRENT_DIR, '..', 'eaglepy310', 'Lib', 'site-packages'))
sys.stdout.reconfigure(encoding='utf-8')

import requests, urllib3
urllib3.disable_warnings()
from videodl import videodl

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

class AnyCipherAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *a, **kw):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers('DEFAULT:@SECLEVEL=0')
        kw['ssl_context'] = ctx
        return super().init_poolmanager(*a, **kw)

# Parse
print("Parsing...", flush=True)
client = videodl.VideoClient(allowed_video_sources=[])
infos = client.parsefromurl("https://v.douyin.com/SkCPSv3WlME/")
info = infos[0]
title = info.get('title', '')
source = info.get('source', '')
ext = info.get('ext', 'mp4')
dl_url = info.get('download_url', '')
headers = dict(info.get('default_download_headers', {}) or {})

print(f"Title: {title}", flush=True)
print(f"Source: {source}", flush=True)
print(f"URL: {str(dl_url)[:120]}", flush=True)

# Safe filename - use simple ASCII + numbers
safe_name = f"douyin_{hash(title) & 0xFFFFFFFF:08x}.{ext}"
save_path = os.path.join(DESKTOP, safe_name)
print(f"Save as: {safe_name}", flush=True)

# Download
s = requests.Session()
s.mount('https://', AnyCipherAdapter())

hdrs = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'}
if headers:
    hdrs.update(headers)

resp = s.get(dl_url, headers=hdrs, stream=True, timeout=60, verify=False)
resp.raise_for_status()

total = int(resp.headers.get('Content-Length', 0))
downloaded = 0
tmp = save_path + '.part'

import time
start = time.time()
last = start

with open(tmp, 'wb') as f:
    for chunk in resp.iter_content(chunk_size=65536):
        if chunk:
            f.write(chunk)
            downloaded += len(chunk)
            now = time.time()
            if now - last >= 1:
                pct = int(downloaded / total * 100) if total else 0
                spd = downloaded / max(now - start, 0.001)
                print(f"  {pct}% {spd/1e6:.1f}MB/s {downloaded/1e6:.1f}/{total/1e6:.1f}MB", flush=True)
                last = now

os.replace(tmp, save_path)
sz_mb = os.path.getsize(save_path) / 1e6
print(f"Done! {sz_mb:.1f} MB -> {save_path}", flush=True)
