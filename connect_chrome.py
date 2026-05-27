import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

WS_URL = "http://127.0.0.1:9222"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(WS_URL)

    # 打开一个新标签页
    page = browser.new_page()
    page.goto("https://www.baidu.com")

    print(f"已打开页面: {page.title()}")
    print(f"页面 URL: {page.url}")

    print("连接成功，浏览器保持打开。")
