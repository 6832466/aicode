import asyncio
from playwright.async_api import async_playwright


async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        contexts = browser.contexts
        pages = contexts[0].pages if contexts else []
        print(f"Open pages: {len(pages)}")
        for i, pg in enumerate(pages):
            print(f"  [{i}] {pg.url[:80]}")

        # find doubao page
        doubao_page = None
        for pg in pages:
            if "doubao.com" in pg.url:
                doubao_page = pg
                break

        if not doubao_page:
            print("Doubao page not found, navigating...")
            doubao_page = pages[0] if pages else await contexts[0].new_page()
            await doubao_page.goto("https://www.doubao.com/chat/", wait_until="networkidle", timeout=30000)

        print(f"\nUsing page: {doubao_page.url}")
        await doubao_page.wait_for_load_state("domcontentloaded", timeout=15000)

        title = await doubao_page.title()
        print(f"Title: {title}")

        # probe input area
        selectors = [
            "textarea",
            "[contenteditable]",
            "[data-testid]",
            "[placeholder]",
        ]
        print("\n--- Input-related elements ---")
        for sel in selectors:
            els = await doubao_page.query_selector_all(sel)
            for el in els[:5]:
                tag = await el.evaluate("el => el.tagName")
                placeholder = await el.get_attribute("placeholder") or ""
                testid = await el.get_attribute("data-testid") or ""
                cls = (await el.get_attribute("class") or "")[:60]
                visible = await el.is_visible()
                if visible:
                    print(f"  [{sel}] tag={tag} testid={testid!r} placeholder={placeholder[:50]!r} class={cls!r}")

        # probe send button
        print("\n--- Button elements (visible) ---")
        btns = await doubao_page.query_selector_all("button")
        for btn in btns[:20]:
            visible = await btn.is_visible()
            if not visible:
                continue
            testid = await btn.get_attribute("data-testid") or ""
            aria = await btn.get_attribute("aria-label") or ""
            text = (await btn.inner_text()).strip()[:30]
            cls = (await btn.get_attribute("class") or "")[:60]
            print(f"  button testid={testid!r} aria={aria!r} text={text!r} class={cls!r}")

        # probe mode switch area
        print("\n--- Mode/model switch elements ---")
        mode_sels = [
            "[data-testid*='model']",
            "[data-testid*='mode']",
            "[class*='model']",
            "[class*='mode']",
            "[class*='switch']",
        ]
        for sel in mode_sels:
            els = await doubao_page.query_selector_all(sel)
            for el in els[:3]:
                visible = await el.is_visible()
                if not visible:
                    continue
                tag = await el.evaluate("el => el.tagName")
                testid = await el.get_attribute("data-testid") or ""
                text = (await el.inner_text()).strip()[:40]
                cls = (await el.get_attribute("class") or "")[:60]
                print(f"  [{sel}] tag={tag} testid={testid!r} text={text!r} class={cls!r}")

        # dump full page HTML snippet around input
        print("\n--- Page body snippet (first 3000 chars) ---")
        body = await doubao_page.evaluate("() => document.body.innerHTML")
        print(body[:3000])


asyncio.run(inspect())
