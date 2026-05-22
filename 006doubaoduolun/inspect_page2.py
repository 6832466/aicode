import asyncio
from playwright.async_api import async_playwright


async def deep_inspect():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # check login state
        print("=== LOGIN STATE ===")
        login_btn = await page.query_selector("button:has-text('登录')")
        print(f"Login button visible: {login_btn is not None}")

        # get textarea details
        print("\n=== TEXTAREA ===")
        ta = await page.query_selector("textarea")
        if ta:
            cls = await ta.get_attribute("class")
            ph = await ta.get_attribute("placeholder")
            print(f"class: {cls}")
            print(f"placeholder: {ph}")
            # get parent chain
            parent_html = await ta.evaluate("""el => {
                let node = el;
                let chain = [];
                for (let i = 0; i < 5; i++) {
                    node = node.parentElement;
                    if (!node) break;
                    chain.push(node.tagName + (node.id ? '#'+node.id : '') + (node.className ? '.'+node.className.split(' ')[0] : ''));
                }
                return chain.join(' > ');
            }""")
            print(f"parent chain: {parent_html}")

        # find send button - look for SVG buttons near textarea
        print("\n=== SEND BUTTON AREA (HTML around textarea) ===")
        area_html = await page.evaluate("""() => {
            const ta = document.querySelector('textarea');
            if (!ta) return 'no textarea';
            // go up 4 levels to get the input container
            let node = ta;
            for (let i = 0; i < 4; i++) node = node.parentElement;
            return node.outerHTML.substring(0, 4000);
        }""")
        print(area_html)

        # look for model/mode switch
        print("\n=== MODEL SWITCH AREA ===")
        model_html = await page.evaluate("""() => {
            // look for elements containing 专家/思考/快速
            const all = document.querySelectorAll('*');
            const results = [];
            for (const el of all) {
                const t = el.innerText || '';
                if ((t.includes('专家') || t.includes('思考') || t.includes('快速')) && t.length < 20) {
                    results.push({
                        tag: el.tagName,
                        text: t.trim(),
                        cls: el.className.substring(0, 80),
                        testid: el.getAttribute('data-testid') || '',
                        outerHTML: el.outerHTML.substring(0, 200)
                    });
                }
            }
            return results.slice(0, 10);
        }""")
        import json
        print(json.dumps(model_html, ensure_ascii=False, indent=2))

        # look for new chat button
        print("\n=== NEW CHAT / SIDEBAR ===")
        new_chat = await page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            const results = [];
            for (const el of all) {
                const t = el.innerText || '';
                if (t.includes('新建') && t.length < 15) {
                    results.push({
                        tag: el.tagName,
                        text: t.trim(),
                        cls: el.className.substring(0, 80),
                        href: el.getAttribute('href') || '',
                        outerHTML: el.outerHTML.substring(0, 200)
                    });
                }
            }
            return results.slice(0, 5);
        }""")
        print(json.dumps(new_chat, ensure_ascii=False, indent=2))


asyncio.run(deep_inspect())
