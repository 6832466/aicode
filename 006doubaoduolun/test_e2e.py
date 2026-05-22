"""
End-to-end test: send a real message to doubao and collect the reply.
Confirms all selectors work correctly before rewriting automation.py.
"""
import asyncio
import time
from playwright.async_api import async_playwright


# Confirmed selectors from page inspection
SELECTORS = {
    # textarea for input
    "input": "textarea.semi-input-textarea",
    # send button - has stable id
    "send_btn": "#flow-end-msg-send",
    # stop button (appears while generating) - find by SVG path or look for it
    # mode dropdown trigger - find by lightning bolt SVG path M13.6552
    "mode_trigger_svg": "M13.6552",
    # new chat - sidebar link
    "new_chat": 'a[href^="/chat/"]',
    # reply container - need to confirm
    "reply": '[class*="receive"], [class*="reply"], [class*="assistant"]',
}


async def find_mode_trigger(page):
    """Find the mode dropdown trigger button by its SVG path."""
    return await page.evaluate("""() => {
        const triggers = document.querySelectorAll('[data-slot="dropdown-menu-trigger"]');
        for (const t of triggers) {
            for (const path of t.querySelectorAll('path')) {
                if ((path.getAttribute('d') || '').startsWith('M13.6552')) {
                    // return the inner clickable button
                    const inner = t.querySelector('button');
                    return inner ? inner.id || 'found_no_id' : 'no_inner_btn';
                }
            }
        }
        return null;
    }""")


async def get_stop_button(page):
    """Check if stop button exists (generation in progress)."""
    return await page.evaluate("""() => {
        // stop button appears during generation - look for square/stop icon
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            if (b.offsetParent === null) continue;
            const r = b.getBoundingClientRect();
            // stop button is near send button position (bottom right of input)
            if (r.x > 1100 && r.y > 1200) {
                const paths = Array.from(b.querySelectorAll('path')).map(p => p.getAttribute('d') || '');
                return {
                    id: b.id,
                    cls: b.className.substring(0, 60),
                    paths: paths.map(d => d.substring(0, 40))
                };
            }
        }
        return null;
    }""")


async def get_last_reply(page):
    """Get the last assistant reply text."""
    return await page.evaluate("""() => {
        // look for message containers - doubao uses specific class patterns
        const candidates = [
            ...document.querySelectorAll('[class*="receive_message"]'),
            ...document.querySelectorAll('[class*="receiveMessage"]'),
            ...document.querySelectorAll('[class*="assistant-message"]'),
            ...document.querySelectorAll('[class*="bot-message"]'),
        ];

        // also try finding by structure: messages after user messages
        const allMsgs = document.querySelectorAll('[class*="message"]');

        if (candidates.length > 0) {
            return {
                method: 'direct',
                count: candidates.length,
                last: candidates[candidates.length - 1].innerText.trim().substring(0, 200)
            };
        }

        // fallback: get all message-like divs
        const msgDivs = Array.from(document.querySelectorAll('div'))
            .filter(d => {
                const cls = d.className || '';
                return cls.includes('message') || cls.includes('chat') || cls.includes('bubble');
            })
            .filter(d => d.offsetParent !== null && d.innerText.trim().length > 10);

        return {
            method: 'fallback',
            count: msgDivs.length,
            classes: msgDivs.slice(-3).map(d => d.className.substring(0, 60)),
            last: msgDivs.length > 0 ? msgDivs[msgDivs.length - 1].innerText.trim().substring(0, 200) : null
        };
    }""")


async def e2e_test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        print("=== E2E TEST: Send message to Doubao ===\n")

        # Step 1: verify send button exists
        send_btn = await page.query_selector("#flow-end-msg-send")
        print(f"Send button found: {send_btn is not None}")

        # Step 2: type message
        print("\nStep 1: Typing message...")
        textarea = page.locator("textarea.semi-input-textarea")
        await textarea.click()
        await page.keyboard.type("请回复「收到测试」四个字，不要说其他内容。")
        await page.wait_for_timeout(300)

        # verify send button is now enabled
        send_info = await page.evaluate("""() => {
            const btn = document.getElementById('flow-end-msg-send');
            if (!btn) return null;
            const r = btn.getBoundingClientRect();
            return {disabled: btn.disabled, rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}};
        }""")
        print(f"Send button state: {send_info}")

        # Step 3: click send
        print("\nStep 2: Clicking send button...")
        t_send = time.time()
        await page.click("#flow-end-msg-send")
        print(f"Sent at t={time.time()-t_send:.2f}s")

        await page.wait_for_timeout(1000)
        await page.screenshot(path="doubao_after_send.png")
        print("Screenshot: doubao_after_send.png")

        # Step 4: wait for stop button to appear (generation started)
        print("\nStep 3: Waiting for generation to start...")
        for i in range(10):
            stop = await get_stop_button(page)
            if stop:
                print(f"  Stop button appeared: {stop}")
                break
            await page.wait_for_timeout(500)
            print(f"  Waiting... {i*0.5:.1f}s")

        # Step 5: wait for stop button to disappear (generation done)
        print("\nStep 4: Waiting for generation to complete...")
        t_start = time.time()
        for i in range(120):  # max 60s
            stop = await get_stop_button(page)
            elapsed = time.time() - t_start
            if not stop:
                print(f"  Generation complete at {elapsed:.1f}s")
                break
            if i % 4 == 0:
                print(f"  Still generating... {elapsed:.1f}s")
            await page.wait_for_timeout(500)

        await page.wait_for_timeout(500)
        await page.screenshot(path="doubao_reply_received.png")
        print("Screenshot: doubao_reply_received.png")

        # Step 6: collect reply
        print("\nStep 5: Collecting reply...")
        reply_info = await get_last_reply(page)
        print(f"Reply info: {reply_info}")

        # Step 7: dump all message-like elements for selector discovery
        print("\nStep 6: Discovering reply selectors...")
        msg_discovery = await page.evaluate("""() => {
            // find the chat message area
            const chatArea = document.querySelector('[class*="chat-content"], [class*="message-list"], [class*="conversation"]');

            // get all text-containing divs in the main content area
            const mainContent = document.querySelector('main, [role="main"], #chat-route-main');
            if (!mainContent) return {error: 'no main content'};

            const allDivs = Array.from(mainContent.querySelectorAll('div, article, section'))
                .filter(d => {
                    const t = d.innerText.trim();
                    return t.length > 5 && t.length < 500 && d.children.length < 5;
                })
                .map(d => ({
                    cls: d.className.substring(0, 80),
                    text: d.innerText.trim().substring(0, 100),
                    tag: d.tagName
                }))
                .slice(-20);  // last 20 elements

            return allDivs;
        }""")
        print("Last message elements:")
        for el in msg_discovery[-10:]:
            print(f"  cls={el['cls'][:60]!r} text={el['text']!r}")

        print("\n=== TEST COMPLETE ===")


asyncio.run(e2e_test())
