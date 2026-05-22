"""Diagnose mode menu content and reply selector on a fresh chat page."""
import asyncio
import time
from playwright.async_api import async_playwright


async def diagnose():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        print("URL:", page.url)

        # 1. Open mode dropdown and dump ALL portal content
        print("\n=== OPENING MODE DROPDOWN ===")
        clicked = await page.evaluate("""() => {
            const triggers = document.querySelectorAll('[data-slot="dropdown-menu-trigger"]');
            for (const t of triggers) {
                for (const path of t.querySelectorAll('path')) {
                    if ((path.getAttribute('d') || '').startsWith('M13.6552')) {
                        const inner = t.querySelector('button');
                        if (inner) { inner.click(); return 'clicked id=' + t.id; }
                    }
                }
            }
            return 'not found';
        }""")
        print(f"Click result: {clicked}")
        await page.wait_for_timeout(800)
        await page.screenshot(path="diag_mode_open.png")

        # dump ALL portal content
        portal_content = await page.evaluate("""() => {
            const results = [];
            // all radix portals
            for (const portal of document.querySelectorAll('[data-radix-popper-content-wrapper]')) {
                const style = window.getComputedStyle(portal);
                results.push({
                    type: 'popper',
                    display: style.display,
                    visibility: style.visibility,
                    text: portal.innerText.trim().substring(0, 500),
                    html: portal.innerHTML.substring(0, 1000)
                });
            }
            // all role=menu
            for (const menu of document.querySelectorAll('[role="menu"]')) {
                results.push({
                    type: 'menu',
                    text: menu.innerText.trim().substring(0, 500),
                    html: menu.innerHTML.substring(0, 1000)
                });
            }
            // all role=listbox
            for (const lb of document.querySelectorAll('[role="listbox"]')) {
                results.push({
                    type: 'listbox',
                    text: lb.innerText.trim().substring(0, 500)
                });
            }
            return results;
        }""")
        print(f"Portals/menus found: {len(portal_content)}")
        for item in portal_content:
            print(f"\n  type={item['type']!r} display={item.get('display')!r}")
            print(f"  text={item['text']!r}")
            if item.get('html'):
                print(f"  html={item['html'][:300]!r}")

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        # 2. Check reply selector on current page
        print("\n=== REPLY SELECTOR CHECK ===")
        # send a test message first
        await page.locator("textarea.semi-input-textarea").click()
        await page.keyboard.type("请回复「诊断测试」四个字")
        await page.wait_for_timeout(200)
        await page.click("#flow-end-msg-send")
        print("Message sent, waiting for reply...")

        # wait and check selectors
        for i in range(40):
            await page.wait_for_timeout(500)
            result = await page.evaluate("""() => {
                const sel1 = document.querySelectorAll('.whitespace-pre-wrap.wrap-anywhere');
                const sel2 = document.querySelectorAll('[class*="receive"]');
                const sel3 = document.querySelectorAll('[class*="assistant"]');
                // also check all elements with substantial text that appeared recently
                const allText = Array.from(document.querySelectorAll('*'))
                    .filter(el => el.children.length === 0 && el.innerText.trim().length > 3 && el.innerText.trim().length < 100)
                    .map(el => ({cls: el.className.substring(0, 60), text: el.innerText.trim()}))
                    .filter(el => el.text.includes('诊断') || el.text.includes('测试'));
                return {
                    sel1_count: sel1.length,
                    sel1_last: sel1.length > 0 ? sel1[sel1.length-1].innerText.trim().substring(0, 100) : null,
                    sel2_count: sel2.length,
                    sel3_count: sel3.length,
                    matching_text: allText
                };
            }""")
            if result['sel1_count'] > 0 or result['matching_text']:
                print(f"  t={i*0.5:.1f}s: sel1={result['sel1_count']} last={result['sel1_last']!r}")
                print(f"  matching: {result['matching_text']}")
                break
            if i % 6 == 0:
                print(f"  t={i*0.5:.1f}s: sel1={result['sel1_count']} sel2={result['sel2_count']}")

        # final state
        await page.wait_for_timeout(2000)
        final = await page.evaluate("""() => {
            // dump all text nodes with substantial content in the chat area
            const main = document.querySelector('#chat-route-main') || document.body;
            const textEls = Array.from(main.querySelectorAll('*'))
                .filter(el => {
                    const t = el.innerText.trim();
                    return el.children.length < 3 && t.length > 5 && t.length < 500;
                })
                .map(el => ({
                    cls: el.className.substring(0, 80),
                    text: el.innerText.trim().substring(0, 100),
                    tag: el.tagName
                }))
                .slice(-15);
            return textEls;
        }""")
        print("\nLast 15 text elements in chat area:")
        for el in final:
            print(f"  {el['tag']} cls={el['cls'][:60]!r} text={el['text']!r}")


asyncio.run(diagnose())
