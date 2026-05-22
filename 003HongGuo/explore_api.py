"""Explore api.fqnovel.com for full video playback endpoints"""
import requests
import json
import re
import urllib.parse

with open('.hongguo_template.json', 'r') as f:
    template = json.load(f)

report = json.loads(template['report_params'])
vid = report['content_id']

# Parse zlink
zlink = template['zlink']
parsed = urllib.parse.urlparse(zlink)
query = urllib.parse.parse_qs(parsed.query)
scheme_str = query.get('schemeParams', [''])[0]
scheme = json.loads(urllib.parse.unquote(scheme_str))
series_id = scheme.get('video_series_id', '')

print(f'vid: {vid}')
print(f'series_id: {series_id}')

session = requests.Session()
session.headers.update({
    'User-Agent': 'com.phoenix.read/7.1.9.32 (Linux; Android 12; zh_CN)',
    'Accept': 'application/json',
})

# 1. Get detail page and look for video URLs in SSR data
print('\n=== 1. Detail page SSR analysis ===')
resp = session.get(f'https://novelquickapp.com/detail?series_id={series_id}', timeout=15)
ssr_marker = 'window._ROUTER_DATA = '
start = resp.text.find(ssr_marker)
json_start = resp.text.find('{', start)
depth = 0
ssr_data = None
for i in range(json_start, len(resp.text)):
    if resp.text[i] == '{':
        depth += 1
    elif resp.text[i] == '}':
        depth -= 1
        if depth == 0:
            ssr_data = json.loads(resp.text[json_start:i+1])
            break

if ssr_data:
    detail = ssr_data.get('loaderData', {}).get('detail_page', {}).get('seriesDetail', {})
    print(f'Name: {detail.get("series_name", "")}')
    print(f'Episode count: {detail.get("episode_count", "")}')
    print(f'Accessible episodes: {detail.get("accessible_episode_cnt", "")}')
    print(f'Has play info: {detail.get("has_play_info", "")}')

    # Check all keys for video URLs
    def find_video_urls(obj, path=''):
        results = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if 'play_url' in k.lower() or 'video_url' in k.lower() or 'main_url' in k.lower():
                    results.append((f'{path}.{k}', str(v)[:200]))
                results.extend(find_video_urls(v, f'{path}.{k}'))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                results.extend(find_video_urls(v, f'{path}[{i}]'))
        return results

    urls = find_video_urls(detail)
    print(f'\nVideo URL keys in detail:')
    for path, val in urls:
        print(f'  {path}: {val}')

# 2. Try api.fqnovel.com endpoints
print('\n=== 2. API endpoint exploration ===')
api_endpoints = [
    ('GET', f'https://api.fqnovel.com/reading/bookapi/video/play/?video_id={vid}'),
    ('GET', f'https://api.fqnovel.com/reading/bookapi/short_video/detail/?video_id={vid}'),
    ('GET', f'https://api.fqnovel.com/novel_ug/novel_platform/v1/video/play_info?video_id={vid}'),
    ('GET', f'https://api.fqnovel.com/novel_ug/novel_platform/v1/series/detail?series_id={series_id}'),
    ('POST', f'https://api.fqnovel.com/novel_ug/novel_platform/v1/video/play_info', {'video_id': vid}),
    ('GET', f'https://api.fqnovel.com/reading/bookapi/book_extra/v?book_id={series_id}'),
]

for method, url, *args in [(e[0], e[1], *e[2:]) for e in api_endpoints]:
    data = args[0] if args else None
    try:
        if method == 'GET':
            resp = session.get(url, timeout=10)
        else:
            resp = session.post(url, json=data, timeout=10)
        body = resp.text[:400]
        print(f'{method} {url[:100]}')
        print(f'  Status: {resp.status_code}, Body: {body}')
        if resp.status_code == 200:
            try:
                j = resp.json()
                print(f'  JSON keys: {list(j.keys())[:10]}')
            except:
                pass
        print()
    except Exception as e:
        print(f'{method} {url[:100]}')
        print(f'  Error: {e}')
        print()

# 3. Search for any other video domains in detail page
print('\n=== 3. CDN/Video domain search in detail page ===')
all_urls = re.findall(r'https?://[a-zA-Z0-9][-a-zA-Z0-9.]*\.(?:com|cn|net)/[^\s"\'<>]{5,}', resp.text)
video_domains = set()
for u in all_urls:
    domain = re.match(r'https?://([^/]+)', u).group(1)
    if any(kw in domain.lower() for kw in ['video', 'vod', 'play', 'qzn', 'novel', 'reading', 'byte', 'snssdk', 'fqnovel', 'toutiao', 'cdn']):
        video_domains.add(u)
for u in sorted(video_domains)[:30]:
    print(f'  {u[:200]}')
