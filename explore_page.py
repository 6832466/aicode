"""探路脚本 - 导航到目标页面并保存 HTML 结构"""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

USER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playwright_profile")
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR, headless=False,
        args=["--start-maximized"], no_viewport=True,
    )
    page = context.new_page()

    # 直接打开详情页
    detail_url = "https://www.shortdramas.com/page/copyright/short-play/short-play-detail/7638309560469441560?from=book"
    print(f"打开详情页: {detail_url}")
    page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    # 点击抖音原生经营
    print("点击 抖音原生经营...")
    try:
        page.click("text='抖音原生经营'", timeout=10000)
        page.wait_for_timeout(5000)
    except Exception as e:
        print(f"失败: {e}")

    # 点击 原生素材 tab
    print("点击 原生素材...")
    try:
        page.click(".arco-tabs-header-title:has-text('原生素材')", timeout=10000)
        page.wait_for_timeout(5000)
    except Exception as e:
        print(f"点击原生素材失败: {e}")
        try:
            page.click("text='原生素材'", timeout=10000)
            page.wait_for_timeout(5000)
        except Exception as e2:
            print(f"备选也失败: {e2}")

    # 处理弹窗
    for btn_text in ["我知道了", "知道了", "确定"]:
        try:
            btn = page.query_selector(f"button:has-text('{btn_text}')")
            if btn and btn.is_visible():
                btn.click()
                print(f"关闭了'{btn_text}'弹窗")
                page.wait_for_timeout(1500)
        except Exception:
            pass

    # 截图
    page.screenshot(path=os.path.join(DESKTOP, "explore_screenshot.png"), full_page=True)
    print("截图已保存")

    # 保存页面HTML（只保存body主要内容）
    html = page.inner_html("body")
    html_path = os.path.join(DESKTOP, "explore_body.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML已保存: {html_path}")

    # 提取所有可见文本
    text = page.inner_text("body")
    text_path = os.path.join(DESKTOP, "explore_text.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"文本已保存: {text_path}")

    # 查找所有包含关键词的元素
    keywords = ["延伸", "素材", "剧情", "预告", "花絮", "回顾", "解析"]
    seen = set()
    elements = page.query_selector_all("[class*='tab'], [class*='menu'], [class*='nav'], button, a, span, div, th, td")
    for el in elements:
        try:
            txt = el.inner_text().strip()
            for kw in keywords:
                if kw in txt and txt not in seen:
                    seen.add(txt)
                    tag = page.evaluate("(el) => el.tagName", el)
                    cls = page.evaluate("(el) => el.className", el)
                    print(f"  [{kw}] <{tag} class='{cls[:60]}'> '{txt[:120]}'")
        except Exception:
            pass

    # 查找表格结构
    tables = page.query_selector_all("table")
    print(f"\n找到 {len(tables)} 个表格")
    for i, t in enumerate(tables):
        rows = t.query_selector_all("tr")
        print(f"  表格{i}: {len(rows)} 行")
        if rows:
            try:
                print(f"    首行: {rows[0].inner_text()[:150]}")
            except Exception:
                pass

    print("\n浏览器保持打开，请检查。完成后关闭窗口。")
    try:
        while True:
            page.wait_for_timeout(1000)
            try:
                page.title()
            except Exception:
                break
    except KeyboardInterrupt:
        pass
