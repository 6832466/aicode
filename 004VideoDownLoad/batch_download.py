import sys, os, ssl, time, copy

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CURRENT_DIR, '..', 'eaglepy310', 'Lib', 'site-packages'))
sys.stdout.reconfigure(encoding='utf-8')

import requests
import urllib3
urllib3.disable_warnings()

from videodl import videodl

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

URLS = [
    "https://v.douyin.com/SkCPSv3WlME/",
    "https://v.kuaishou.com/Kdt9wi7I",
    "https://www.bilibili.com/video/BV1He23BQErf/",
    "https://www.youtube.com/watch?v=tfeCwDT-5m0",
]

class AnyCipherAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *a, **kw):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers('DEFAULT:@SECLEVEL=0')
        kw['ssl_context'] = ctx
        return super().init_poolmanager(*a, **kw)

def download(url, path, headers=None):
    s = requests.Session()
    s.mount('https://', AnyCipherAdapter())
    hdrs = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'}
    if headers:
        hdrs.update(headers)

    # Strategy 1: direct HTTPS
    resp = None
    for strat_idx, (proto_url, verify) in enumerate([
        (url, False),
        (url.replace('https://', 'http://'), False),
    ]):
        try:
            resp = s.get(proto_url, headers=hdrs, stream=True, timeout=(30, 120), verify=verify)
            resp.raise_for_status()
            break
        except Exception as e:
            if strat_idx == 0:
                print(f"  HTTPS失败, 尝试HTTP... ({e})", flush=True)
            else:
                raise

    if resp is None:
        raise RuntimeError("所有下载策略均失败")

    total = int(resp.headers.get('Content-Length', 0))
    downloaded = 0
    start = time.time()
    last = start
    tmp = path + '.part'
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(tmp, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if now - last >= 1.0:
                    pct = int(downloaded / total * 100) if total > 0 else 0
                    elapsed = now - start
                    spd = downloaded / max(elapsed, 0.001)
                    spd_s = f"{spd/1e6:.1f}MB/s" if spd > 1e6 else f"{spd/1e3:.0f}KB/s"
                    sz = f"{total/1e6:.1f}MB" if total else "?"
                    print(f"    {pct}% {spd_s} {downloaded/1e6:.1f}/{sz}", flush=True)
                    last = now

    os.replace(tmp, path)
    return path

print(f"桌面: {DESKTOP}", flush=True)

results = []
for i, url in enumerate(URLS, 1):
    print(f"\n{'='*60}", flush=True)
    print(f"[{i}/4] {url[:100]}", flush=True)

    try:
        client = videodl.VideoClient(allowed_video_sources=[])
        infos = client.parsefromurl(url)

        if not infos:
            print("  [FAIL] 无解析结果", flush=True)
            results.append((url, False, "无解析结果"))
            continue

        info = infos[0]
        err = info.get('err_msg', '')
        if err:
            print(f"  [FAIL] 解析错误: {err}", flush=True)
            results.append((url, False, err))
            continue

        title = info.get('title', '未知')
        source = info.get('source', '?')
        ext = info.get('ext', 'mp4')
        dl_url = info.get('download_url', '')
        headers = dict(info.get('default_download_headers', {}) or {})

        print(f"  标题: {title}", flush=True)
        print(f"  平台: {source} 格式: {ext}", flush=True)
        print(f"  URL: {str(dl_url)[:120]}", flush=True)

        safe = "".join(c for c in title if c not in r'\/:*?"<>|')[:80]
        fname = f"{safe}.{ext}"
        spath = os.path.join(DESKTOP, fname)

        print(f"  保存: {fname}", flush=True)
        print(f"  下载中...", flush=True)

        result = download(dl_url, spath, headers)
        if result and os.path.exists(result):
            sz = os.path.getsize(result) / 1e6
            print(f"  [OK] {sz:.1f} MB", flush=True)
            results.append((url, True, result))
        else:
            print(f"  [FAIL] 下载后文件不存在", flush=True)
            results.append((url, False, "文件不存在"))

    except Exception as e:
        print(f"  [FAIL] {e}", flush=True)
        results.append((url, False, str(e)))

print(f"\n{'='*60}", flush=True)
ok = sum(1 for r in results if r[1])
print(f"成功: {ok} / 失败: {len(results)-ok}", flush=True)
for r in results:
    s = "OK" if r[1] else "FAIL"
    detail = os.path.basename(r[2]) if r[1] else str(r[2])[:60]
    print(f"  [{s}] {r[0][:60]} -> {detail}", flush=True)
