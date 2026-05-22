"""Diagnose mode menu HTML and reply selector."""
import asyncio
import time
from playwright.async_api import async_playwright


async def diagnose2():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        print("URL:", page.url)

        # === 1. Open mode dropdown and get full HTML ===
        print("\n=== MODE DROPDOWN HTML ===")
        await page.evaluate("""() => {
            const triggers = document.querySelectorAll('[data-slot="dropdown-menu-trigger"]');
            for (const t of triggers) {
                for (const path of t.querySelectorAll('path')) {
                    if ((path.getAttribute('d') || '').startsWith('M13.6552')) {
                        const inner = t.querySelector('button');
                        if (inner) { inner.click(); return; }
                    }
                }
            }
        }""")
        await page.wait_for_timeout(1000)

        # get the full menu HTML
        menu_html = await page.evaluate("""() => {
            const portals = document.querySelectorAll('[data-radix-popper-content-wrapper]');
            const results = [];
            for (const portal of portals) {
                const menu = portal.querySelector('[role="menu"]');
                if (menu) {
                    results.push({
                        full_html: menu.outerHTML.substring(0, 3000),
                        inner_text: menu.innerText,
                        children_count: menu.children.length
                    });
                }
            }
            return results;
        }""")
        for m in menu_html:
            print(f"children: {m['children_count']}")
            print(f"innerText: {m['inner_text']!r}")
            print(f"HTML:\n{m['full_html']}")

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        # === 2. Check reply selector - send a message and watch ===
        print("\n=== REPLY SELECTOR TEST ===")
        await page.locator("textarea.semi-input-textarea").click()
        await page.keyboard.type("请回复「OK」两个字")
        await page.wait_for_timeout(200)
        await page.click("#flow-end-msg-send")
        print("Sent. Watching for reply...")

        for i in range(60):
            await page.wait_for_timeout(500)
            result = await page.evaluate("""() => {
                try {
                    const sel1 = document.querySelectorAll('.whitespace-pre-wrap.wrap-anywhere');
                    const sel1_texts = Array.from(sel1).map(el => (el.innerText || '').trim().substring(0, 50));

                    // also look for any element containing OK or 收到
                    const allEls = document.querySelectorAll('*');
                    const matching = [];
                    for (const el of allEls) {
                        if (el.children.length === 0) {
                            const t = (el.innerText || el.textContent || '').trim();
                            if (t.includes('OK') || t.includes('收到') || t.includes('好的')) {
                                matching.push({cls: el.className.substring(0, 60), text: t.substring(0, 50)});
                            }
                        }
                    }
                    return {sel1_count: sel1.length, sel1_texts, matching};
                } catch(e) {
                    return {error: e.message};
                }
            }""")
            if result.get('error'):
                print(f"  JS error: {result['error']}")
                continue
            if result['sel1_count'] > 0 or result['matching']:
                print(f"  t={i*0.5:.1f}s: sel1={result['sel1_count']} texts={result['sel1_texts']}")
                print(f"  matching: {result['matching']}")
                break
            if i % 4 == 0:
                print(f"  t={i*0.5:.1f}s: sel1={result['sel1_count']}")

        # take screenshot
        await page.screenshot(path="diag_reply.png")
        print("Screenshot: diag_reply.png")

        # dump last elements in chat
        final = await page.evaluate("""() => {
            try {
                const main = document.querySelector('#chat-route-main') || document.body;
                const results = [];
                const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
                let node;
                while (node = walker.nextNode()) {
                    const t = node.textContent.trim();
                    if (t.length > 3 && t.length < 200) {
                        const parent = node.parentElement;
                        results.push({
                            tag: parent ? parent.tagName : 'unknown',
                            cls: parent ? parent.className.substring(0, 60) : '',
                            text: t.substring(0, 80)
                        });
                    }
                }
                return results.slice(-20);
            } catch(e) {
                return [{error: e.message}];
            }
        }""")
        print("\nLast text nodes in chat:")
        for el in final:
            if el.get('error'):
                print(f"  ERROR: {el['error']}")
            else:
                print(f"  {el['tag']} cls={el['cls'][:50]!r} text={el['text']!r}")


asyncio.run(diagnose2())
