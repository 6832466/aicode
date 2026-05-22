import asyncio
import json
from playwright.async_api import async_playwright


async def inspect_v3():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # screenshot
        await page.screenshot(path="doubao_screenshot.png", full_page=False)
        print("Screenshot saved: doubao_screenshot.png")

        # get all text content properly encoded
        result = await page.evaluate("""() => {
            const info = {};

            // textarea
            const ta = document.querySelector('textarea');
            info.textarea_placeholder = ta ? ta.placeholder : null;
            info.textarea_class = ta ? ta.className : null;

            // all buttons with text
            const btns = Array.from(document.querySelectorAll('button'));
            info.buttons = btns
                .filter(b => b.offsetParent !== null)  // visible
                .map(b => ({
                    text: b.innerText.trim().substring(0, 30),
                    cls: b.className.substring(0, 60),
                    testid: b.getAttribute('data-testid') || '',
                    id: b.id || '',
                    slot: b.getAttribute('data-slot') || ''
                }))
                .filter(b => b.text.length > 0)
                .slice(0, 30);

            // look for model selector - dropdown trigger
            const dropdowns = Array.from(document.querySelectorAll('[data-slot="dropdown-menu-trigger"]'));
            info.dropdowns = dropdowns.map(d => ({
                tag: d.tagName,
                text: d.innerText.trim().substring(0, 40),
                cls: d.className.substring(0, 60),
                id: d.id || ''
            }));

            // look for send button by position (bottom right of input area)
            // find all SVG buttons
            const svgBtns = Array.from(document.querySelectorAll('button svg')).map(svg => {
                const btn = svg.closest('button');
                return {
                    text: btn.innerText.trim().substring(0, 20),
                    cls: btn.className.substring(0, 80),
                    testid: btn.getAttribute('data-testid') || '',
                    ariaLabel: btn.getAttribute('aria-label') || '',
                    type: btn.type || ''
                };
            });
            info.svg_buttons = svgBtns.slice(0, 15);

            // check login state
            info.page_title = document.title;
            info.has_login_form = !!document.querySelector('input[type="password"]');
            info.body_text_sample = document.body.innerText.substring(0, 500);

            return info;
        }""")

        print("\n=== PAGE INFO ===")
        print(f"Title: {result['page_title']}")
        print(f"Has login form: {result['has_login_form']}")
        print(f"\nTextarea placeholder: {result['textarea_placeholder']}")
        print(f"Textarea class: {result['textarea_class']}")

        print("\n=== VISIBLE BUTTONS ===")
        for b in result['buttons']:
            print(f"  text={b['text']!r} testid={b['testid']!r} id={b['id']!r} slot={b['slot']!r}")

        print("\n=== DROPDOWN TRIGGERS ===")
        for d in result['dropdowns']:
            print(f"  {d['tag']} text={d['text']!r} id={d['id']!r}")

        print("\n=== SVG BUTTONS ===")
        for b in result['svg_buttons']:
            print(f"  text={b['text']!r} aria={b['ariaLabel']!r} testid={b['testid']!r} cls={b['cls'][:60]!r}")

        print("\n=== BODY TEXT SAMPLE ===")
        print(result['body_text_sample'])


asyncio.run(inspect_v3())
