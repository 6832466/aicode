import asyncio
from playwright.async_api import async_playwright


async def check_state():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        print("URL:", page.url)
        await page.screenshot(path="after_send_state.png")

        # get all message content using the class we discovered
        msgs = await page.evaluate("""() => {
            const replies = document.querySelectorAll('.whitespace-pre-wrap');
            return Array.from(replies).map(el => ({
                cls: el.className.substring(0, 100),
                text: el.innerText.trim().substring(0, 300),
                visible: el.offsetParent !== null
            })).filter(el => el.text.length > 0);
        }""")
        print(f"Messages with whitespace-pre-wrap: {len(msgs)}")
        for m in msgs:
            print(f"  visible={m['visible']} text={m['text'][:120]!r}")
            print(f"  cls={m['cls']!r}")

        # also check for stop button / generation indicator
        gen_state = await page.evaluate("""() => {
            // look for stop button (square icon during generation)
            const allBtns = Array.from(document.querySelectorAll('button'))
                .filter(b => b.offsetParent !== null);
            const bottomBtns = allBtns.filter(b => {
                const r = b.getBoundingClientRect();
                return r.x > 1050 && r.y > 1150;
            });
            return bottomBtns.map(b => {
                const r = b.getBoundingClientRect();
                const paths = Array.from(b.querySelectorAll('path')).map(p => (p.getAttribute('d') || '').substring(0, 50));
                return {
                    id: b.id,
                    rect: {x: Math.round(r.x), y: Math.round(r.y)},
                    paths: paths.slice(0, 2)
                };
            });
        }""")
        print(f"\nBottom-right buttons: {gen_state}")

        # check if there's a loading/streaming indicator
        loading = await page.evaluate("""() => {
            const indicators = [
                ...document.querySelectorAll('[class*="loading"]'),
                ...document.querySelectorAll('[class*="streaming"]'),
                ...document.querySelectorAll('[class*="generating"]'),
                ...document.querySelectorAll('[class*="typing"]'),
            ];
            return indicators
                .filter(el => el.offsetParent !== null)
                .map(el => ({cls: el.className.substring(0, 60), text: el.innerText.trim().substring(0, 30)}));
        }""")
        print(f"Loading indicators: {loading}")


asyncio.run(check_state())
