"""Quick debug: find Gemini HD image URL."""
import sys, os, time, tempfile
sys.path.insert(0, r"E:\AiCode\005flow2api")
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

WS_URL = "ws://127.0.0.1:9222/devtools/browser/2eb4069e-a3fb-41e6-9247-18a2f370cb0f"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(WS_URL)

    page = None
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if "gemini.google.com" in pg.url:
                page = pg
                break
        if page:
            break

    if not page:
        print("Opening new Gemini page...")
        page = browser.contexts[0].new_page()
        page.goto("https://gemini.google.com/app", timeout=30000)
        page.wait_for_timeout(5000)

    page.bring_to_front()
    cdp = page.context.new_cdp_session(page)

    # Generate image
    print("[1] Selecting image tool...")
    page.evaluate("""() => {
        const btn = document.querySelector('button[aria-label="上传和工具"]');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(1000)
    img_btn = page.locator('button:has-text("制作图片")').first
    img_btn.click(force=True, timeout=3000)
    page.wait_for_timeout(1000)

    print("[2] Typing prompt...")
    input_box = page.locator('div[role="textbox"]').first
    input_box.click()
    page.wait_for_timeout(300)
    input_box.fill("画一只可爱的猫")
    page.wait_for_timeout(500)

    print("[3] Sending...")
    page.locator('button[aria-label*="发送"]').first.click()

    print("[4] Waiting for image...")
    deadline = time.time() + 120
    found = False
    while time.time() < deadline:
        page.wait_for_timeout(2000)
        try:
            imgs = page.locator("img.image.animate.loaded")
            if imgs.count() > 0:
                found = True
                break
        except Exception:
            continue

    if not found:
        print("ERROR: No image!")
        exit(1)

    # Get detailed image info
    print("\n=== IMAGE & DOWNLOAD INFO ===")
    info = page.evaluate("""() => {
        const result = {images: [], download_buttons: [], links: [], all_buttons: []};

        // All images
        document.querySelectorAll('img').forEach((img, i) => {
            const src = img.src || '';
            if (src && !src.startsWith('data:image/svg+xml')) {
                result.images.push({
                    idx: i,
                    src: src.substring(0, 400),
                    naturalW: img.naturalWidth,
                    naturalH: img.naturalHeight,
                    className: img.className?.substring(0, 200),
                    parent: img.parentElement?.tagName,
                    grandparent: img.parentElement?.parentElement?.tagName,
                });
            }
        });

        // ALL links
        document.querySelectorAll('a').forEach((a, i) => {
            const href = a.href || '';
            if (href) {
                result.links.push({
                    idx: i,
                    href: href.substring(0, 500),
                    text: a.textContent?.trim()?.substring(0, 100),
                    download: a.getAttribute('download') || '',
                });
            }
        });

        // Buttons with download/image/share related text
        document.querySelectorAll('button').forEach(b => {
            const label = b.getAttribute('aria-label') || '';
            const text = (b.textContent || '').trim();
            if (label.includes('下载') || text.includes('下载') ||
                label.includes('download') || text.includes('download') ||
                label.includes('分享') || text.includes('分享') ||
                label.includes('复制') || text.includes('复制') ||
                label.includes('重做') || text.includes('重做')) {
                result.download_buttons.push({
                    label,
                    text: text.substring(0, 200),
                    tag: b.tagName,
                    rect: JSON.stringify(b.getBoundingClientRect()),
                });
            }
        });

        return result;
    }""")

    print("--- Images ---")
    for img in info.get("images", []):
        print(f"  [{img['idx']}] {img['naturalW']}x{img['naturalH']} cls={img['className']}")
        print(f"      src={img['src']}")

    print("\n--- Download/Share Buttons ---")
    for b in info.get("download_buttons", []):
        print(f"  [{b['tag']}] aria={b['label']} text={b['text']} rect={b.get('rect')}")

    print("\n--- Links with URLs ---")
    for l in info.get("links", []):
        print(f"  [{l['idx']}] {l['href']} download={l['download']}")

    # Now try: the image-container might have a surrounding anchor
    # Check for any element that wraps the image
    print("\n--- Image element parent chain ---")
    parent_info = page.evaluate("""() => {
        const imgs = document.querySelectorAll('img.image');
        if (imgs.length === 0) return [];
        const img = imgs[imgs.length - 1];
        let el = img.parentElement;
        const chain = [];
        for (let i = 0; i < 10 && el; i++) {
            chain.push({
                level: i,
                tag: el.tagName,
                className: el.className?.substring(0, 200),
                hasHref: !!el.href,
                href: (el.href || '').substring(0, 300),
                onclick: (el.onclick?.toString() || '').substring(0, 200),
                role: el.getAttribute('role') || '',
                ariaLabel: el.getAttribute('aria-label') || '',
            });
            el = el.parentElement;
        }
        return chain;
    }""")
    for p in parent_info:
        print(f"  L{p['level']} <{p['tag']}> cls={p['className']} role={p['role']} aria={p['ariaLabel']} href={p['href']}")

    # Now click download and watch for new pages
    print("\n--- Clicking download button... ---")
    pages_before = {pg.url for ctx in browser.contexts for pg in ctx.pages}

    rect = page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            const label = b.getAttribute('aria-label') || '';
            const text = b.textContent || '';
            if (label.includes('下载完整尺寸') || text.includes('下载完整尺寸') ||
                label.includes('download full') || text.includes('download full')) {
                const r = b.getBoundingClientRect();
                return {x: r.left + r.width/2, y: r.top + r.height/2, label, visible: r.width > 0 && r.height > 0};
            }
        }
        return null;
    }""")

    if rect and rect["visible"]:
        # Set up download behavior BEFORE clicking (important!)
        dl_dir = tempfile.mkdtemp(prefix="gemini_hd_")
        cdp.send("Browser.setDownloadBehavior", {
            "behavior": "allowAndName",
            "downloadPath": dl_dir.replace("\\", "/"),
            "eventsEnabled": True,
        })

        cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": rect["x"], "y": rect["y"]})
        time.sleep(0.05)
        cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": rect["x"], "y": rect["y"], "button": "left", "clickCount": 1})
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": rect["x"], "y": rect["y"], "button": "left", "clickCount": 1})

        time.sleep(3)

        # Check new pages
        pages_after = {pg.url for ctx in browser.contexts for pg in ctx.pages}
        new = pages_after - pages_before
        print(f"New pages: {[u[:200] for u in new]}")

        # Check download dir
        for f in os.listdir(dl_dir):
            fpath = os.path.join(dl_dir, f)
            print(f"Download file: {f} = {os.path.getsize(fpath)} bytes")

        # Also check if any image opened in current page
        print(f"\nCurrent page URL: {page.url[:200]}")
    else:
        print("Download button NOT FOUND or not visible!")

    browser.close()
