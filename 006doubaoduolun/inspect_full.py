import asyncio
import json
from playwright.async_api import async_playwright


async def full_inspect():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        result = await page.evaluate("""() => {
            const info = {};

            // 1. textarea
            const ta = document.querySelector('textarea');
            info.textarea = ta ? {
                placeholder: ta.placeholder,
                cls: ta.className,
                parent4_html: (() => {
                    let n = ta;
                    for (let i = 0; i < 6; i++) n = n.parentElement;
                    return n ? n.outerHTML.substring(0, 2000) : '';
                })()
            } : null;

            // 2. all visible buttons with full details
            info.all_buttons = Array.from(document.querySelectorAll('button'))
                .filter(b => b.offsetParent !== null)
                .map(b => ({
                    text: b.innerText.trim().substring(0, 30),
                    cls: b.className.substring(0, 100),
                    testid: b.getAttribute('data-testid') || '',
                    id: b.id || '',
                    slot: b.getAttribute('data-slot') || '',
                    ariaLabel: b.getAttribute('aria-label') || '',
                    type: b.type,
                    disabled: b.disabled,
                    rect: (() => {
                        const r = b.getBoundingClientRect();
                        return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                    })()
                }));

            // 3. find the send button - it should be near the bottom right of textarea
            const taRect = ta ? ta.getBoundingClientRect() : null;
            if (taRect) {
                info.textarea_rect = {x: Math.round(taRect.x), y: Math.round(taRect.y), w: Math.round(taRect.width), h: Math.round(taRect.height)};
                // buttons near textarea bottom
                info.buttons_near_input = info.all_buttons.filter(b =>
                    b.rect.y > taRect.y - 50 && b.rect.y < taRect.bottom + 100
                );
            }

            // 4. model dropdown - click it to see options
            info.dropdown_trigger = (() => {
                const d = document.querySelector('[data-slot="dropdown-menu-trigger"]');
                return d ? {
                    text: d.innerText.trim(),
                    id: d.id,
                    cls: d.className.substring(0, 80)
                } : null;
            })();

            // 5. new chat button
            info.new_chat = Array.from(document.querySelectorAll('a, button, div[role="button"]'))
                .filter(el => el.offsetParent !== null)
                .filter(el => {
                    const t = el.innerText || '';
                    return t.includes('新对话') || t.includes('新建') || t.includes('新建对话');
                })
                .map(el => ({
                    tag: el.tagName,
                    text: el.innerText.trim().substring(0, 30),
                    href: el.getAttribute('href') || '',
                    cls: el.className.substring(0, 80)
                }))
                .slice(0, 5);

            return info;
        }""")

        print("=== TEXTAREA ===")
        if result["textarea"]:
            print(f"placeholder: {result['textarea']['placeholder']}")
            print(f"class: {result['textarea']['cls']}")
            print(f"rect: {result.get('textarea_rect')}")
            print(f"\nParent HTML (6 levels up):\n{result['textarea']['parent4_html']}")

        print("\n=== BUTTONS NEAR INPUT ===")
        for b in result.get("buttons_near_input", []):
            print(f"  text={b['text']!r} id={b['id']!r} testid={b['testid']!r} aria={b['ariaLabel']!r} rect={b['rect']} cls={b['cls'][:60]!r}")

        print("\n=== ALL VISIBLE BUTTONS ===")
        for b in result.get("all_buttons", []):
            print(f"  text={b['text']!r} id={b['id']!r} testid={b['testid']!r} aria={b['ariaLabel']!r} rect={b['rect']}")

        print("\n=== DROPDOWN TRIGGER ===")
        print(result.get("dropdown_trigger"))

        print("\n=== NEW CHAT ===")
        for n in result.get("new_chat", []):
            print(f"  {n}")

        # now click the dropdown to see model options
        print("\n=== CLICKING MODEL DROPDOWN ===")
        dropdown = await page.query_selector('[data-slot="dropdown-menu-trigger"]')
        if dropdown:
            await dropdown.click()
            await page.wait_for_timeout(800)
            await page.screenshot(path="doubao_dropdown.png")
            print("Dropdown screenshot saved")

            menu_items = await page.evaluate("""() => {
                const items = document.querySelectorAll('[role="menuitem"], [data-slot="dropdown-menu-item"], [data-radix-collection-item]');
                return Array.from(items).map(el => ({
                    text: el.innerText.trim().substring(0, 50),
                    cls: el.className.substring(0, 80),
                    role: el.getAttribute('role') || ''
                }));
            }""")
            print("Menu items:")
            for item in menu_items:
                print(f"  text={item['text']!r} role={item['role']!r} cls={item['cls'][:60]!r}")

            # close dropdown
            await page.keyboard.press("Escape")


asyncio.run(full_inspect())
