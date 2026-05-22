import asyncio
from playwright.async_api import async_playwright


async def test_mode_and_send():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # === TEST 1: Click mode dropdown (快速 button = id radix-:rk:) ===
        print("=== TEST 1: Mode dropdown ===")
        # The outer trigger is id="radix-:rk:" with data-slot="dropdown-menu-trigger"
        # The inner button has the actual text and SVG
        mode_trigger = page.locator('[data-slot="dropdown-menu-trigger"]').nth(2)  # 3rd dropdown trigger = mode
        box = await mode_trigger.bounding_box()
        print(f"Mode trigger box: {box}")

        # click the inner button (the visible one)
        inner_btn = mode_trigger.locator("button").first
        inner_box = await inner_btn.bounding_box()
        print(f"Inner button box: {inner_box}")

        await inner_btn.click()
        await page.wait_for_timeout(800)
        await page.screenshot(path="doubao_mode_open.png")
        print("Screenshot saved: doubao_mode_open.png")

        # get menu items
        items = await page.evaluate("""() => {
            const results = [];
            // try all possible menu item selectors
            for (const sel of ['[role="menuitem"]', '[role="option"]', '[data-radix-collection-item]']) {
                for (const el of document.querySelectorAll(sel)) {
                    if (el.offsetParent !== null) {
                        results.push({
                            sel,
                            text: el.innerText.trim().substring(0, 60),
                            cls: el.className.substring(0, 80),
                            role: el.getAttribute('role') || ''
                        });
                    }
                }
            }
            // also look for any visible popup/menu
            const menus = document.querySelectorAll('[data-radix-popper-content-wrapper], [role="menu"]');
            const menuInfo = Array.from(menus).map(m => ({
                visible: m.offsetParent !== null,
                text: m.innerText.trim().substring(0, 200),
                cls: m.className.substring(0, 60)
            }));
            return { items: results, menus: menuInfo };
        }""")

        print("Menu items found:")
        for item in items["items"]:
            print(f"  {item['text']!r} role={item['role']!r}")
        print("Menus found:")
        for m in items["menus"]:
            print(f"  visible={m['visible']} text={m['text']!r}")

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        # === TEST 2: Type a message and find send button ===
        print("\n=== TEST 2: Type message ===")
        textarea = page.locator("textarea.semi-input-textarea")
        await textarea.click()
        await textarea.fill("你好，这是一条测试消息，请回复「收到」两个字即可。")
        await page.wait_for_timeout(500)
        await page.screenshot(path="doubao_typed.png")
        print("Screenshot saved: doubao_typed.png")

        # find send button after typing (it should appear)
        send_info = await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            return btns
                .filter(b => b.offsetParent !== null)
                .map(b => {
                    const r = b.getBoundingClientRect();
                    const paths = Array.from(b.querySelectorAll('path')).map(p => p.getAttribute('d') || '').slice(0, 1);
                    return {
                        text: b.innerText.trim().substring(0, 20),
                        id: b.id,
                        cls: b.className.substring(0, 80),
                        rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                        svgPath: paths[0] ? paths[0].substring(0, 40) : '',
                        disabled: b.disabled
                    };
                })
                .filter(b => b.rect.y > 1200);  // only buttons in input area
        }""")
        print("Buttons in input area after typing:")
        for b in send_info:
            print(f"  text={b['text']!r} id={b['id']!r} rect={b['rect']} disabled={b['disabled']} svg={b['svgPath']!r}")

        # clear the textarea
        await textarea.fill("")
        print("\nTextarea cleared")


asyncio.run(test_mode_and_send())
