import asyncio
from playwright.async_api import async_playwright


async def test_interactions():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # --- Step 1: enumerate all dropdown triggers with their text ---
        print("=== ALL DROPDOWN TRIGGERS ===")
        triggers = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('[data-slot="dropdown-menu-trigger"]'))
                .map((el, i) => {
                    const r = el.getBoundingClientRect();
                    return {
                        index: i,
                        id: el.id,
                        text: el.innerText.trim().substring(0, 30),
                        visible: el.offsetParent !== null,
                        rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}
                    };
                });
        }""")
        for t in triggers:
            print(f"  [{t['index']}] id={t['id']!r} text={t['text']!r} visible={t['visible']} rect={t['rect']}")

        # --- Step 2: click mode button by id ---
        print("\n=== CLICKING MODE BUTTON BY ID ===")
        # From previous inspection: id="radix-:rk:" is the mode dropdown trigger
        # But radix IDs are dynamic. Use the inner button with the lightning bolt SVG path
        mode_btn_id = await page.evaluate("""() => {
            // find the dropdown trigger that contains the mode SVG (lightning bolt path starts with M13.6552)
            const triggers = document.querySelectorAll('[data-slot="dropdown-menu-trigger"]');
            for (const t of triggers) {
                const paths = t.querySelectorAll('path');
                for (const path of paths) {
                    const d = path.getAttribute('d') || '';
                    if (d.startsWith('M13.6552')) {
                        return t.id;
                    }
                }
            }
            return null;
        }""")
        print(f"Mode button id: {mode_btn_id!r}")

        if mode_btn_id:
            # click the inner visible button
            clicked = await page.evaluate(f"""() => {{
                const trigger = document.getElementById('{mode_btn_id}');
                if (!trigger) return 'trigger not found';
                const innerBtn = trigger.querySelector('button');
                if (!innerBtn) return 'inner button not found';
                innerBtn.click();
                return 'clicked';
            }}""")
            print(f"Click result: {clicked}")
            await page.wait_for_timeout(800)
            await page.screenshot(path="doubao_mode_open.png")
            print("Screenshot: doubao_mode_open.png")

            # get menu items
            menu_items = await page.evaluate("""() => {
                const results = [];
                // radix dropdown renders in a portal
                const portals = document.querySelectorAll('[data-radix-popper-content-wrapper]');
                for (const portal of portals) {
                    if (portal.offsetParent !== null || portal.style.display !== 'none') {
                        results.push({
                            type: 'portal',
                            text: portal.innerText.trim().substring(0, 300),
                            html: portal.innerHTML.substring(0, 500)
                        });
                    }
                }
                // also check role=menu
                for (const menu of document.querySelectorAll('[role="menu"]')) {
                    results.push({
                        type: 'menu',
                        text: menu.innerText.trim().substring(0, 300)
                    });
                }
                return results;
            }""")
            print("Menu content:")
            for m in menu_items:
                print(f"  type={m['type']!r} text={m['text']!r}")

            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)

        # --- Step 3: type a message and find send button ---
        print("\n=== TYPING MESSAGE ===")
        textarea = page.locator("textarea.semi-input-textarea")
        await textarea.click()
        await page.keyboard.type("你好，这是测试消息")
        await page.wait_for_timeout(500)
        await page.screenshot(path="doubao_typed.png")
        print("Screenshot: doubao_typed.png")

        # find send button - appears after typing
        send_btns = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button'))
                .filter(b => b.offsetParent !== null)
                .map(b => {
                    const r = b.getBoundingClientRect();
                    const paths = Array.from(b.querySelectorAll('path')).map(p => p.getAttribute('d') || '');
                    return {
                        text: b.innerText.trim().substring(0, 20),
                        id: b.id,
                        cls: b.className.substring(0, 60),
                        rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                        svgPaths: paths.map(d => d.substring(0, 50)),
                        disabled: b.disabled
                    };
                })
                .filter(b => b.rect.y > 1150 && b.rect.w > 0);
        }""")
        print("Buttons in input area after typing:")
        for b in send_btns:
            print(f"  text={b['text']!r} id={b['id']!r} rect={b['rect']} disabled={b['disabled']}")
            for path in b['svgPaths'][:1]:
                print(f"    svg: {path!r}")

        # clear
        await textarea.fill("")
        print("\nCleared textarea")

        # --- Step 4: find new chat button ---
        print("\n=== NEW CHAT BUTTON ===")
        new_chat = await page.evaluate("""() => {
            // look for the + icon button in sidebar (new conversation)
            const allEls = document.querySelectorAll('a[href^="/chat/"], button, div[role="button"]');
            const results = [];
            for (const el of allEls) {
                const t = el.innerText.trim();
                const r = el.getBoundingClientRect();
                if (r.x < 300 && r.w > 0 && r.h > 0) {  // sidebar area
                    results.push({
                        tag: el.tagName,
                        text: t.substring(0, 30),
                        href: el.getAttribute('href') || '',
                        cls: el.className.substring(0, 60),
                        rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}
                    });
                }
            }
            return results.slice(0, 10);
        }""")
        for n in new_chat:
            print(f"  {n['tag']} text={n['text']!r} href={n['href']!r} rect={n['rect']}")


asyncio.run(test_interactions())
