import asyncio
import json
from playwright.async_api import async_playwright


async def inspect_send_and_mode():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 1. Find send button - it's near the textarea, bottom right
        result = await page.evaluate("""() => {
            const ta = document.querySelector('textarea');
            const taRect = ta.getBoundingClientRect();

            // get the input container (go up until we find the full input box)
            let container = ta;
            for (let i = 0; i < 8; i++) container = container.parentElement;
            const containerHTML = container.outerHTML.substring(0, 5000);

            // find all buttons in the input area
            const allBtns = Array.from(container.querySelectorAll('button'));
            const btnInfo = allBtns.map(b => {
                const r = b.getBoundingClientRect();
                return {
                    text: b.innerText.trim().substring(0, 20),
                    cls: b.className.substring(0, 100),
                    id: b.id,
                    slot: b.getAttribute('data-slot') || '',
                    rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                    svgPaths: Array.from(b.querySelectorAll('path')).map(p => p.getAttribute('d') || '').slice(0, 1).map(d => d.substring(0, 60)),
                    disabled: b.disabled,
                    visible: b.offsetParent !== null
                };
            });

            return {
                containerHTML,
                buttons: btnInfo,
                taRect: {x: Math.round(taRect.x), y: Math.round(taRect.y), w: Math.round(taRect.width), h: Math.round(taRect.height), bottom: Math.round(taRect.bottom)}
            };
        }""")

        print("=== TEXTAREA RECT ===")
        print(result["taRect"])

        print("\n=== BUTTONS IN INPUT CONTAINER ===")
        for b in result["buttons"]:
            print(f"  text={b['text']!r} id={b['id']!r} slot={b['slot']!r} rect={b['rect']} visible={b['visible']} disabled={b['disabled']}")
            if b['svgPaths']:
                print(f"    svg_path_start={b['svgPaths'][0]!r}")

        print("\n=== INPUT CONTAINER HTML ===")
        print(result["containerHTML"])

        # 2. Click the mode button (快速 button) to see dropdown
        print("\n\n=== CLICKING MODE BUTTON ===")
        # find the button with text containing 快速
        mode_btn = await page.locator("button", has_text="快速").first
        if mode_btn:
            box = await mode_btn.bounding_box()
            print(f"Mode button box: {box}")
            await mode_btn.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path="doubao_mode_dropdown.png")
            print("Mode dropdown screenshot saved")

            # get dropdown items
            items = await page.evaluate("""() => {
                const selectors = [
                    '[role="menuitem"]',
                    '[role="option"]',
                    '[data-radix-collection-item]',
                    '[data-slot="dropdown-menu-item"]',
                    '[data-slot="select-item"]'
                ];
                const results = [];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        results.push({
                            sel,
                            text: el.innerText.trim().substring(0, 60),
                            cls: el.className.substring(0, 80),
                            role: el.getAttribute('role') || '',
                            value: el.getAttribute('data-value') || el.getAttribute('value') || ''
                        });
                    }
                }
                return results;
            }""")
            print("Dropdown items:")
            for item in items:
                print(f"  sel={item['sel']!r} text={item['text']!r} role={item['role']!r} value={item['value']!r}")

            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)


asyncio.run(inspect_send_and_mode())
