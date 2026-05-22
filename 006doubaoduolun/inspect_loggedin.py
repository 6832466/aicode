import asyncio
from playwright.async_api import async_playwright


async def screenshot_after_login():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # don't reload, just take screenshot of current state
        await page.screenshot(path="doubao_loggedin.png")
        print("Screenshot saved: doubao_loggedin.png")

        result = await page.evaluate("""() => {
            return {
                url: location.href,
                body: document.body.innerText.substring(0, 400),
                has_textarea: !!document.querySelector('textarea'),
                textarea_placeholder: document.querySelector('textarea')?.placeholder || null,
                buttons: Array.from(document.querySelectorAll('button'))
                    .filter(b => b.offsetParent !== null && b.innerText.trim())
                    .map(b => b.innerText.trim().substring(0, 25))
                    .slice(0, 20)
            }
        }""")

        print("URL:", result["url"])
        print("Has textarea:", result["has_textarea"])
        print("Textarea placeholder:", result["textarea_placeholder"])
        print("Buttons:", result["buttons"])
        print("\nBody text:\n", result["body"])


asyncio.run(screenshot_after_login())
