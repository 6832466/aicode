import requests, urllib.request

proxies = {}
try:
    p = urllib.request.getproxies()
    if p.get('http'):
        proxies = {'http': p['http'], 'https': p['https']}
except: pass

resp = requests.get('https://api.bilibili.com/x/web-interface/view?bvid=BV1He23BQErf',
                    headers={'User-Agent': 'Mozilla/5.0'}, proxies=proxies)
cid = resp.json()['data']['cid']

# Compare qn=80 vs qn=127 with fnval=4048 (which enables 4K+dash+HDR+dolby)
for qn in [80, 112, 116, 120, 127]:
    r = requests.get(
        f'https://api.bilibili.com/x/player/playurl?otype=json&fnver=0&fnval=4048&qn={qn}&bvid=BV1He23BQErf&cid={cid}&platform=html5',
        headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com'},
        proxies=proxies, timeout=5)
    result = r.json()
    durls = result.get('data', {}).get('durl', [])
    if durls:
        # Get the largest one
        best = max(durls, key=lambda x: x.get('size', 0))
        url = best.get('url', '')
        print(f'qn={qn:3d} size={best.get("size",0)/1024/1024:.1f}MB url_preview={url[:80]}')

# Also test fnval=0 (original behavior)
print()
for qn in [80, 127]:
    r = requests.get(
        f'https://api.bilibili.com/x/player/playurl?otype=json&fnver=0&fnval=0&qn={qn}&bvid=BV1He23BQErf&cid={cid}&platform=html5',
        headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com'},
        proxies=proxies, timeout=5)
    result = r.json()
    durls = result.get('data', {}).get('durl', [])
    if durls:
        best = max(durls, key=lambda x: x.get('size', 0))
        print(f'fnval=0 qn={qn:3d} size={best.get("size",0)/1024/1024:.1f}MB')
