"""Download 红果短剧 APK and extract API endpoints"""
import requests
import re
import sys
import urllib.parse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
OUTPUT_DIR = "e:/AiCode/003HongGuo"

session = requests.Session()
session.headers.update(HEADERS)

# Approach 1: Try apk.support
print("=== Approach 1: apk.support ===")
resp = session.get("https://apk.support/download-app/com.phoenix.read", timeout=30)
print(f"Status: {resp.status_code}, Length: {len(resp.text)}")

# Find download links
apk_links = re.findall(r'https?://[^\s"\'<>]+\.apk[^\s"\'<>]*', resp.text)
dl_links = re.findall(r'https?://[^\s"\'<>]+download[^\s"\'<>]+com\.phoenix[^\s"\'<>]*', resp.text)
all_links = apk_links + dl_links
print(f"APK/DL links found: {len(all_links)}")
for link in all_links[:10]:
    print(f"  {link[:300]}")

# Look for onclick or data attributes with download URLs
data_urls = re.findall(r'(?:data-url|data-link|data-href)=["\']([^"\']+)["\']', resp.text)
for u in data_urls:
    if "phoenix" in u.lower() or "download" in u.lower():
        print(f"  data-url: {u[:200]}")

# Approach 2: Try Evozi form submission
print("\n=== Approach 2: Evozi form submission ===")
resp2 = session.get("https://apps.evozi.com/apk-downloader/", timeout=15)
csrf_match = re.findall(r'name="_token"[^>]*value="([^"]+)"', resp2.text)
if csrf_match:
    csrf = csrf_match[0]
    print(f"CSRF: {csrf[:40]}...")

    post_data = {
        "_token": csrf,
        "id": "com.phoenix.read",
        "type": "package_name",
    }
    resp3 = session.post("https://apps.evozi.com/apk-downloader/", data=post_data, timeout=30)
    print(f"POST status: {resp3.status_code}, Length: {len(resp3.text)}")

    # Find download links
    urls = re.findall(r'https?://[^\s"\'<>]+', resp3.text)
    for u in urls:
        if "apk" in u.lower() or "phoenix" in u.lower() or "download" in u.lower():
            print(f"  URL: {u[:300]}")

# Approach 3: Direct APK download from common mirrors
print("\n=== Approach 3: Direct mirror download ===")
mirrors = [
    f"https://apkpure.com/hong-guo-mian-fei-xiao-shuo-re-men-xiao-shuo-mian-fei-kan/com.phoenix.read/download?from=details",
    f"https://m.apkpure.com/hong-guo-mian-fei-xiao-shuo-re-men-xiao-shuo-mian-fei-kan/com.phoenix.read/download",
]

for url in mirrors:
    try:
        r = session.head(url, timeout=15, allow_redirects=True)
        print(f"HEAD {url[:80]}: {r.status_code} -> {r.url[:200]}")
    except Exception as e:
        print(f"HEAD {url[:80]}: ERROR {e}")

# Approach 4: Can we use Google Play?
print("\n=== Approach 4: Google Play info ===")
resp4 = session.get("https://play.google.com/store/apps/details?id=com.phoenix.read&hl=en", timeout=15)
print(f"Google Play: {resp4.status_code}")
if resp4.status_code == 200:
    title = re.findall(r'<title>([^<]+)</title>', resp4.text)
    print(f"  Title: {title}")

# Approach 5: Try websites that might have the APK hosted
print("\n=== Approach 5: Alternative sites ===")
alt_sites = [
    "https://www.9game.cn/search/?keyword=%E7%BA%A2%E6%9E%9C%E7%9F%AD%E5%89%A7",
    "https://app.mi.com/search?keywords=%E7%BA%A2%E6%9E%9C%E7%9F%AD%E5%89%A7",
]

for site in alt_sites:
    try:
        r = session.get(site, timeout=15)
        print(f"{site[:60]}: {r.status_code}")
        if r.status_code == 200 and "phoenix" in r.text.lower():
            dl = re.findall(r'https?://[^\s"\'<>]+com\.phoenix[^\s"\'<>]*\.apk[^\s"\'<>]*', r.text)
            print(f"  DL links: {dl[:3]}")
    except Exception as e:
        print(f"{site[:60]}: ERROR {e}")
