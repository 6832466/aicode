"""Generate 16:9 image with 3 reference images using Gemini CDP."""
import sys, os, time, base64
sys.path.insert(0, r"E:\AiCode\005flow2api")
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

WS_URL = "ws://127.0.0.1:9222/devtools/browser/2eb4069e-a3fb-41e6-9247-18a2f370cb0f"

REF_IMAGES = [
    r"E:\角色图\111现代人物\3a78bb994d73f9e8741ca0e9868fcfb1cb1fa08f1fa9c5-bfw1tS_fw658webp.jpg",
    r"E:\角色图\111现代人物\32eafaed8dbad87691735842b761b95055a5734d50110-U7y9wj_fw658webp.jpg",
    r"E:\角色图\111现代人物\62d885285d50f1ccf7555e8acec3c29ae0ece32d3e66d-4cvVVn_fw658webp.jpg",
]

PROMPT = """请参考这三张图片中的人物外貌和特征，创作一张 16:9 横屏图片。

要求：
- 保持三个人的面部特征、发型、五官不变
- 给他们设计一个好看的现代都市背景（咖啡厅、书店、或城市街景）
- 16:9 宽屏比例
- 光线柔和，画面高质量，构图美观
- 自然的互动姿态"""

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
        page = browser.contexts[0].new_page()
        page.goto("https://gemini.google.com/app", timeout=30000)
        page.wait_for_timeout(5000)

    page.bring_to_front()
    print(f"Page: {page.url}")

    # Step 1: Select image tool
    print("\n[1] Selecting image generation tool...")
    page.evaluate("""() => {
        const btn = document.querySelector('button[aria-label="上传和工具"]');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(1000)

    img_btn = page.locator('button:has-text("制作图片")').first
    if img_btn.count() > 0 and img_btn.is_visible(timeout=2000):
        img_btn.click(force=True, timeout=3000)
        page.wait_for_timeout(1000)
        print("   Selected 制作图片")
    else:
        print("   ERROR: 制作图片 not found!")
        exit(1)

    # Step 2: Select 3.5 Flash model
    print("\n[2] Selecting model...")
    mode_btn = page.locator('[aria-label*="模式选择器"]').first
    if mode_btn.count() > 0 and mode_btn.is_visible(timeout=2000):
        mode_btn.click(force=True)
        page.wait_for_timeout(800)
        opt = page.locator('[role="menuitem"]:has-text("3.5 Flash")').first
        if opt.count() > 0 and opt.is_visible(timeout=2000):
            opt.click(force=True)
            page.wait_for_timeout(500)
            print("   Selected 3.5 Flash")

    # Step 3: Upload reference images one by one
    print("\n[3] Uploading reference images...")

    # Find the file input
    file_input = page.locator('input[type="file"]')

    for i, img_path in enumerate(REF_IMAGES):
        if not os.path.exists(img_path):
            print(f"   ERROR: {img_path} not found!")
            continue

        print(f"   Uploading [{i+1}/3]: {os.path.basename(img_path)}")

        # Click the upload button if it exists
        upload_btn = page.locator('button[aria-label*="从一张图开始"]').first
        if upload_btn.count() > 0 and upload_btn.is_visible(timeout=2000):
            upload_btn.click(force=True)
            page.wait_for_timeout(500)

        # Upload file
        try:
            file_input.set_input_files(img_path)
            page.wait_for_timeout(2000)
            print(f"   Uploaded!")
        except Exception as e:
            print(f"   Upload error: {e}")
            # Try alternative: use file chooser
            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    upload_btn = page.locator('button[aria-label*="上传"]').first
                    if upload_btn.count() > 0:
                        upload_btn.click()
                fc_info.value.set_files(img_path)
                page.wait_for_timeout(2000)
                print(f"   Uploaded via file chooser!")
            except Exception as e2:
                print(f"   File chooser error: {e2}")

    page.wait_for_timeout(1000)

    # Step 4: Type prompt
    print("\n[4] Typing prompt...")
    input_box = page.locator('div[role="textbox"]').first
    input_box.click()
    page.wait_for_timeout(300)

    # Type in chunks to avoid truncation
    input_box.fill("")
    page.wait_for_timeout(200)
    input_box.type(PROMPT, delay=10)
    page.wait_for_timeout(500)
    print(f"   Prompt typed ({len(PROMPT)} chars)")

    # Step 5: Send
    print("\n[5] Sending...")
    send_btn = page.locator('button[aria-label*="发送"]').first
    send_btn.click()
    print("   Sent — waiting for image...")

    # Step 6: Wait for image
    print("\n[6] Waiting for image...")
    deadline = time.time() + 180
    image_data = None

    while time.time() < deadline:
        page.wait_for_timeout(3000)
        try:
            imgs = page.locator("img.image.animate.loaded")
            count = imgs.count()
            if count > 0:
                last_img = imgs.last
                src = last_img.get_attribute("src") or ""
                print(f"   Image found! src={src[:100]}...")

                # Get blob data
                if src.startswith("data:"):
                    image_data = base64.b64decode(src.split(",", 1)[1])
                elif src.startswith("blob:"):
                    image_data = page.evaluate("""async (src) => {
                        const r = await fetch(src);
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    }""", src)
                    image_data = bytes(image_data)
                elif src.startswith("http"):
                    import urllib.request
                    with urllib.request.urlopen(src) as resp:
                        image_data = resp.read()

                if image_data:
                    print(f"   Downloaded: {len(image_data):,} bytes ({len(image_data)/1024/1024:.2f} MB)")
                    break
        except Exception as e:
            print(f"   Waiting... ({e})")
            continue

    if image_data:
        desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
        out_path = os.path.join(desktop, "gemini_3refs_16x9.png")
        with open(out_path, "wb") as f:
            f.write(image_data)
        print(f"\n✅ Saved: {out_path}")
    else:
        print("\n❌ No image generated within timeout")

    browser.close()
