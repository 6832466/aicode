"""Gemini CDP client — direct browser control via Playwright CDP.

Replaces the flow2api local server for users with their own Gemini account.
Connects to a locally running Chrome with --remote-debugging-port and
automates gemini.google.com for image generation.
"""
from __future__ import annotations

import base64
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from api_client import GenerationResult


# Gemini DOM selectors — updated 2026-05 via live inspection (Chinese UI, Gemini 2026.05).
GEMINI_SELECTORS = {
    "input": 'div[role="textbox"]',
    "send": 'button[aria-label*="发送"]',
    "add_tools": 'button[aria-label="上传和工具"]',
    "upload_file": '[role="menuitem"]:has-text("上传文件")',
    "create_image": 'button:has-text("制作图片")',
    "mode_selector": '[aria-label*="模式选择器"]',
    "upload_from_image": 'button[aria-label*="从一张图开始"]',
    "image_result": "img.image.animate.loaded",
    "image_button": "button.image-button",
    "file_input": 'input[type="file"]',
    "conversation": "message-content",
    "stop_button": 'button[aria-label*="停止"]',
}


class GeminiCDPError(Exception):
    """Errors from Gemini CDP operations."""


@dataclass
class _CDPState:
    playwright: object = None
    browser: object = None
    context: object = None
    page: object = None

    def invalidate(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None


class GeminiCDPClient:
    """Synchronous client that controls gemini.google.com via Chrome CDP.

    Interface mirrors Flow2ApiClient so BatchGenerationManager needs no changes.
    """

    def __init__(self, chrome_host: str = "127.0.0.1", chrome_port: int = 9222,
                 timeout: int = 300):
        self.timeout = timeout
        self._chrome_host = chrome_host
        self._chrome_port = chrome_port
        self._state = _CDPState()
        self._image_count_before = 0
        self._cdp_url = self._resolve_cdp_url(chrome_host, chrome_port)

    @staticmethod
    def _resolve_cdp_url(host: str, port: int) -> str:
        """Detect the best CDP URL. Prefers DevToolsActivePort WS URL
        (Chrome 144+ chrome://inspect mode), falls back to HTTP endpoint."""
        import os
        import sys
        candidates = []
        try:
            localappdata = os.environ.get("LOCALAPPDATA", "")
            candidates.append(os.path.join(localappdata, "Google", "Chrome", "User Data", "DevToolsActivePort"))
        except Exception:
            pass
        # Also try common profile paths
        for candidate in candidates:
            try:
                lines = Path(candidate).read_text().strip().splitlines()
                if len(lines) >= 2:
                    ws_port = lines[0].strip()
                    ws_path = lines[1].strip()
                    ws_url = f"ws://{host}:{ws_port}{ws_path}"
                    print(f"[cdp] Using WebSocket URL from DevToolsActivePort: {ws_url}", file=sys.stderr, flush=True)
                    return ws_url
            except Exception:
                continue
        return f"http://{host}:{port}"

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to Chrome CDP and locate/initialise a Gemini page. Returns True on success."""
        try:
            self._state = self._create_connection()
            return True
        except Exception:
            return False

    def disconnect(self):
        """Disconnect Playwright from Chrome. Does NOT close the browser
        or any pages — the user's Chrome and Gemini tabs stay intact."""
        state, self._state = self._state, _CDPState()
        try:
            if state.playwright is not None:
                state.playwright.stop()
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        try:
            return (
                self._state.browser is not None
                and self._state.browser.is_connected()
            )
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Connection check (standalone, thread-safe)
    # ------------------------------------------------------------------

    def check_connection(self) -> tuple[bool, str]:
        """Test Chrome CDP connectivity and Gemini page presence."""
        import socket
        from urllib.parse import urlparse

        # Re-read DevToolsActivePort for fresh Target ID
        fresh_url = self._resolve_cdp_url(self._chrome_host, self._chrome_port)
        if fresh_url != self._cdp_url:
            self._cdp_url = fresh_url

        # Quick TCP check first — faster than Playwright timeout
        parsed = urlparse(self._cdp_url)
        host = parsed.hostname
        port = parsed.port or 9222
        try:
            s = socket.socket()
            s.settimeout(2)
            s.connect((host, port))
            s.close()
        except Exception:
            return False, (
                f"Chrome 调试端口未开启 ({host}:{port})\n"
                "请开启 Chrome 远程调试:\n"
                "  方式一: chrome.exe --remote-debugging-port=9222\n"
                "  方式二: Chrome 中打开 chrome://inspect/#remote-debugging 并启用"
            )

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(self._cdp_url)
                contexts = browser.contexts
                if not contexts:
                    return False, "Chrome 已连接，但未找到浏览器上下文"
                for ctx in contexts:
                    for page in ctx.pages:
                        if "gemini.google.com" in page.url:
                            return True, "已连接 — 找到 Gemini 页面"
                return True, "Chrome 已连接，但未打开 Gemini 页面 (请手动打开 gemini.google.com)"
        except Exception as e:
            msg = str(e)
            if "Connection refused" in msg or "connect" in msg.lower():
                return False, (
                    f"无法连接 Chrome 调试端口 ({host}:{port})\n"
                    "请开启 Chrome 远程调试:\n"
                    "  方式一: chrome.exe --remote-debugging-port=9222\n"
                    "  方式二: Chrome 中打开 chrome://inspect/#remote-debugging 并启用"
                )
            return False, f"连接失败: {msg[:200]}"

    # ------------------------------------------------------------------
    # Image generation
    # ------------------------------------------------------------------

    def generate_image(
        self,
        prompt: str,
        model: str = "3.5 Flash",
        reference_image: bytes | None = None,
        image_size: str = "",
    ) -> GenerationResult:
        """Generate a single image via Gemini web UI.

        Navigates the existing Gemini page to /app for a fresh conversation
        while preserving browser login. Does NOT close the user's tabs.
        """
        try:
            # Lazy connect on first call
            if not self.is_connected:
                if not self.connect():
                    return GenerationResult(
                        success=False,
                        error_message="Chrome CDP 连接已断开，请重新连接",
                        prompt=prompt,
                    )

            page = self._get_or_create_gemini_page(model)

            # Type prompt FIRST — ensures text is always entered
            # even if upload fails later
            self._type_prompt(page, prompt)

            # Upload reference image if provided (after prompt is typed)
            if reference_image:
                try:
                    self._upload_reference(page, reference_image)
                except GeminiCDPError:
                    raise
                except Exception as e:
                    raise GeminiCDPError(f"上传参考图失败: {e}")

            # Record existing image count to detect new images
            self._image_count_before = self._count_generated_images(page)

            # Click send
            self._click_send(page)

            # Wait for image to appear (display resolution via blob)
            image_data = self._wait_for_image(page)

            if image_data is None:
                return GenerationResult(
                    success=False,
                    error_message=f"[Gemini] 图片生成超时 ({self.timeout}s) 或未找到生成结果",
                    prompt=prompt,
                )

            return GenerationResult(
                success=True,
                image_data=image_data,
                prompt=prompt,
            )

        except GeminiCDPError as e:
            return GenerationResult(
                success=False,
                error_message=f"[Gemini] {e}",
                prompt=prompt,
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                error_message=f"[Gemini] {type(e).__name__}: {e}",
                prompt=prompt,
            )

    def _clean_gemini_tabs(self):
        """Close all Gemini pages/tabs for a clean state without browser restart."""
        import sys
        state = self._state
        if state.browser is None:
            return
        closed = 0
        for ctx in state.browser.contexts:
            for p in list(ctx.pages):
                try:
                    if not p.is_closed() and "gemini.google.com" in (p.url or ""):
                        p.close()
                        closed += 1
                except Exception:
                    pass
        if closed:
            print(f"[clean] closed {closed} Gemini tab(s)", file=sys.stderr, flush=True)
        state.page = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_connection(self) -> _CDPState:
        from playwright.sync_api import sync_playwright

        # Re-read DevToolsActivePort — the Target ID may change after
        # a previous disconnect, especially in chrome://inspect mode.
        fresh_url = self._resolve_cdp_url(self._chrome_host, self._chrome_port)
        if fresh_url != self._cdp_url:
            import sys
            print(f"[cdp] Target ID refreshed: {fresh_url}", file=sys.stderr, flush=True)
            self._cdp_url = fresh_url

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.connect_over_cdp(self._cdp_url)
            # Reuse existing context; prefer one with Gemini already open
            context = None
            gemini_page = None
            for ctx in browser.contexts:
                for p in ctx.pages:
                    if "gemini.google.com" in p.url:
                        context = ctx
                        gemini_page = p
                        break
                if context is not None:
                    break
            if context is None:
                context = browser.contexts[0]
            if gemini_page is not None:
                gemini_page.bring_to_front()
            return _CDPState(playwright=pw, browser=browser, context=context, page=gemini_page)
        except Exception:
            try:
                pw.stop()
            except Exception:
                pass
            raise

    def _get_or_create_gemini_page(self, model: str = "3.5 Flash"):
        """Return a Gemini page with fresh conversation and image generation tool selected."""
        state = self._state

        # Find an existing Gemini page to reuse
        existing = None
        for ctx in state.browser.contexts:
            for p in ctx.pages:
                try:
                    if not p.is_closed() and "gemini.google.com" in p.url:
                        existing = p
                        state.context = ctx
                        break
                except Exception:
                    continue
            if existing:
                break

        if existing:
            try:
                existing.goto("https://gemini.google.com/app", wait_until="commit", timeout=30000)
                existing.wait_for_selector(GEMINI_SELECTORS["input"], timeout=10000)
                existing.wait_for_timeout(2000)
                self._select_image_tool(existing)
                self._select_model(existing, model)
                state.page = existing
                return existing
            except Exception:
                pass

        # No existing page or navigation failed — create a new one
        page = state.context.new_page()
        try:
            page.goto("https://gemini.google.com/app", wait_until="commit", timeout=60000)
        except Exception:
            # Last resort: try any available Gemini page
            for ctx in state.browser.contexts:
                for p in ctx.pages:
                    try:
                        if not p.is_closed() and "gemini.google.com" in p.url:
                            page = p
                            state.context = ctx
                            break
                    except Exception:
                        continue

        try:
            page.wait_for_selector(GEMINI_SELECTORS["input"], timeout=15000)
            page.wait_for_timeout(2000)  # Let JS handlers fully initialize
        except Exception:
            pass
        self._select_image_tool(page)
        self._select_model(page, model)
        state.page = page
        return page

    def _select_image_tool(self, page):
        """Click '上传和工具' → '制作图片' to switch Gemini into image gen mode."""
        import sys

        # 1. Click the "+" (上传和工具) button — use JS to bypass gem-icon interception
        add_btn = page.locator(GEMINI_SELECTORS["add_tools"]).first
        if add_btn.count() == 0:
            print("[tool] '+' button not found, continuing…", file=sys.stderr, flush=True)
            return

        page.evaluate("""() => {
            const btn = document.querySelector('button[aria-label="上传和工具"]');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(800)

        # 2. Find "制作图片" in the expanded overlay
        for sel in [
            GEMINI_SELECTORS["create_image"],
            '.cdk-overlay-container button:has-text("制作图片")',
            '[aria-label*="制作图片"]',
        ]:
            try:
                card = page.locator(sel).first
                if card.count() > 0 and card.is_visible(timeout=2000):
                    card.click(force=True, timeout=3000)
                    page.wait_for_timeout(1000)
                    print(f"[tool] selected 制作图片 via {sel}", file=sys.stderr, flush=True)
                    return
            except Exception:
                continue

        page.keyboard.press("Escape")
        print("[tool] 制作图片 not found, continuing…", file=sys.stderr, flush=True)

    def _select_model(self, page, model_name: str = "3.5 Flash"):
        """Select a model from the mode selector dropdown (e.g. '3.5 Flash', '3.1 Pro')."""
        import sys
        try:
            mode_btn = page.locator(GEMINI_SELECTORS["mode_selector"]).first
            if mode_btn.count() == 0 or not mode_btn.is_visible(timeout=1000):
                print("[mode] mode selector not found", file=sys.stderr, flush=True)
                return
            mode_btn.click(force=True)
            page.wait_for_timeout(800)

            for sel in [
                f'[role="menuitem"]:has-text("{model_name}")',
                f'[role="option"]:has-text("{model_name}")',
                f'.mat-mdc-menu-item:has-text("{model_name}")',
            ]:
                try:
                    opt = page.locator(sel).first
                    if opt.count() > 0 and opt.is_visible(timeout=2000):
                        opt.click(force=True)
                        page.wait_for_timeout(500)
                        print(f"[mode] selected {model_name} via {sel}", file=sys.stderr, flush=True)
                        return
                except Exception:
                    continue

            page.keyboard.press("Escape")
            print(f"[mode] {model_name} not found in dropdown", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[mode] error: {e}", file=sys.stderr, flush=True)

    def _type_prompt(self, page, prompt: str):
        """Type the prompt into Gemini's input box."""
        sel = GEMINI_SELECTORS["input"]
        try:
            page.wait_for_selector(sel, timeout=10000)
        except Exception:
            raise GeminiCDPError("找不到 Gemini 输入框，页面可能已变更")

        # First dismiss any overlay (e.g. reference image thumbnail from prev chat)
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass

        input_el = page.locator(sel).first
        try:
            input_el.click(timeout=5000)
        except Exception:
            # If click is intercepted by overlay, focus via keyboard
            input_el.focus()

        # Select all existing text and replace via keyboard
        page.keyboard.press("Control+a")
        # Prepend prefix so Gemini knows to generate an image
        page.keyboard.insert_text(f"生成图片：{prompt}")

    def _click_send(self, page):
        """Click the send button."""
        for sel in [GEMINI_SELECTORS["send"], 'button[aria-label="发送"]', 'button[aria-label*="Send"]']:
            try:
                btn = page.locator(sel).first
                btn.click(timeout=3000)
                return
            except Exception:
                continue
        # Fallback: press Enter
        page.keyboard.press("Enter")

    def _upload_reference(self, page, image_bytes: bytes):
        """Upload a reference image to Gemini's input area.

        Strategy 1: drag-and-drop via DataTransfer + DragEvent (fast, no UI).
        Strategy 2: pre-load file into JS, hook HTMLInputElement.prototype.click
        to override the files property getter BEFORE Gemini reads it, then
        click '+' → '上传文件' so Gemini sees the file immediately.
        """
        import sys

        tmp = Path(tempfile.gettempdir()) / f"gemini_ref_{int(time.time() * 1000)}.png"
        tmp.write_bytes(image_bytes)
        try:
            b64 = base64.b64encode(image_bytes).decode()

            # ---- Strategy 1: drag-and-drop (no UI interaction) ----
            drop_result = page.evaluate("""
            async (b64data) => {
                try {
                    const resp = await fetch(`data:image/png;base64,${b64data}`);
                    const blob = await resp.blob();
                    const file = new File([blob], 'reference.png', {type: 'image/png'});
                    const dt = new DataTransfer();
                    dt.items.add(file);

                    function makeDragEvent(type, dt) {
                        const ev = new DragEvent(type, {bubbles: true, cancelable: true});
                        Object.defineProperty(ev, 'dataTransfer', {value: dt});
                        return ev;
                    }

                    const targets = [
                        document.querySelector('rich-textarea'),
                        document.querySelector('[role="textbox"]'),
                        document.querySelector('[contenteditable="true"]'),
                    ].filter(Boolean);

                    for (const target of targets) {
                        target.dispatchEvent(makeDragEvent('dragenter', dt));
                        await new Promise(r => setTimeout(r, 30));
                        target.dispatchEvent(makeDragEvent('dragover', dt));
                        await new Promise(r => setTimeout(r, 50));
                        target.dispatchEvent(makeDragEvent('dragover', dt));
                        await new Promise(r => setTimeout(r, 30));
                        target.dispatchEvent(makeDragEvent('drop', dt));
                        await new Promise(r => setTimeout(r, 100));
                        document.body.dispatchEvent(makeDragEvent('drop', dt));
                        await new Promise(r => setTimeout(r, 50));
                    }
                    return 'ok:' + (targets[0]?.tagName || 'body');
                } catch (e) {
                    return 'error:' + e.message;
                }
            }
            """, b64)
            print(f"[upload] S1 drop: {drop_result}", file=sys.stderr, flush=True)

            if self._wait_for_preview(page, label="S1-dragdrop", timeout_s=3.0):
                return

            # ---- Strategy 2: pre-load + hook files getter + UI click ----
            print("[upload] S2 hook+click…", file=sys.stderr, flush=True)

            # Pre-load file data into a global DataTransfer that the hook will use
            page.evaluate("""
            async (b64data) => {
                window.__gemini_dt = null;
                const resp = await fetch(`data:image/png;base64,${b64data}`);
                const blob = await resp.blob();
                const file = new File([blob], 'reference.png', {type: 'image/png'});
                const dt = new DataTransfer();
                dt.items.add(file);
                window.__gemini_dt = dt;
            }
            """, b64)

            # Install hook that overrides files getter on intercepted inputs
            page.evaluate("""
            () => {
                if (!window.__gemini_hook_v2) {
                    window.__gemini_hook_v2 = true;
                    const origClick = HTMLInputElement.prototype.click;
                    HTMLInputElement.prototype.click = function() {
                        if (this.type === 'file' && window.__gemini_dt) {
                            window.__gemini_hook_fired = true;
                            window.__gemini_file_input = this;
                            // Override files getter so Gemini sees our files immediately
                            const dt = window.__gemini_dt;
                            Object.defineProperty(this, 'files', {
                                get: () => dt.files,
                                configurable: true
                            });
                            // Dispatch events after a microtask so Gemini's click
                            // handler can return first, then the change handler fires
                            setTimeout(() => {
                                this.dispatchEvent(new Event('input', {bubbles: true}));
                                this.dispatchEvent(new Event('change', {bubbles: true}));
                            }, 0);
                            return; // Suppress the native file dialog
                        }
                        return origClick.call(this);
                    };
                }
                window.__gemini_hook_fired = false;
                window.__gemini_file_input = null;
            }
            """)

            # Click '+' (上传和工具) button
            clicked_sel = None
            for sel in [
                GEMINI_SELECTORS["add_tools"],
                'button[aria-label*="上传"]',
                'button[aria-label*="添加"]',
                'button[aria-label*="Add"]',
                'button[aria-label*="Upload"]',
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible(timeout=1000):
                        clicked_sel = sel
                        btn.click()
                        page.wait_for_timeout(600)
                        break
                except Exception:
                    continue

            if not clicked_sel:
                raise GeminiCDPError("上传参考图失败 — 找不到 Gemini '+' 按钮")

            print(f"[upload] S2 clicked: {clicked_sel}", file=sys.stderr, flush=True)

            # Click "上传文件" menu item
            menu_ok = False
            for sel in [
                GEMINI_SELECTORS["upload_file"],
                '.cdk-overlay-container [role="menuitem"]:has-text("上传文件")',
                '.cdk-overlay-container button:has-text("上传文件")',
                'button[aria-label*="上传文件"]',
            ]:
                try:
                    opt = page.locator(sel).first
                    if opt.count() > 0 and opt.is_visible(timeout=1000):
                        opt.click()
                        menu_ok = True
                        break
                except Exception:
                    continue

            if not menu_ok:
                # Menu may not appear; try dispatching change on any file input
                pass

            print(f"[upload] S2 menu_ok={menu_ok}", file=sys.stderr, flush=True)

            # Wait for and verify hook fired
            for i in range(15):
                page.wait_for_timeout(400)
                fired = page.evaluate("() => !!window.__gemini_hook_fired")
                if fired:
                    print(f"[upload] S2 hook fired after {(i+1)*0.4:.1f}s", file=sys.stderr, flush=True)
                    break

            if self._wait_for_preview(page, label="S2-hook", timeout_s=8.0):
                return

            # Also try set_input_files as last resort (in case files getter didn't work)
            fis = page.locator('input[type="file"]')
            fc = fis.count()
            print(f"[upload] S2 fallback — {fc} file input(s)", file=sys.stderr, flush=True)
            for j in range(fc):
                try:
                    fis.nth(j).set_input_files(str(tmp))
                except Exception:
                    continue
            if fc > 0:
                page.wait_for_timeout(2000)
                if self._has_upload_preview(page):
                    print("[upload] S2 fallback set_input_files — success", file=sys.stderr, flush=True)
                    return

            raise GeminiCDPError(
                "上传参考图失败 — 两种策略均未检测到预览。"
                "请确认 Gemini 页面处于正常对话状态。"
            )
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass

    def _wait_for_preview(self, page, label: str = "", timeout_s: float = 10.0) -> bool:
        """Poll until an uploaded image preview appears in Gemini's input area."""
        import sys
        deadline = time.time() + timeout_s
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            page.wait_for_timeout(500)
            if self._has_upload_preview(page):
                print(f"[upload] {label} — success after {attempt * 0.5:.1f}s", file=sys.stderr, flush=True)
                return True
            # Periodic debug check — any images near the input area?
            if attempt == 4 or attempt == 10:
                try:
                    js_check = page.evaluate("""
                    () => {
                        const area = document.querySelector('rich-textarea') ||
                                     document.querySelector('[role="textbox"]');
                        if (!area) return 0;
                        const parent = area.closest('form') || area.parentElement || document.body;
                        return parent.querySelectorAll('img, [style*="background-image"]').length;
                    }
                    """)
                    print(f"[upload] {label} — attempt {attempt}, img count near input: {js_check}", file=sys.stderr, flush=True)
                except Exception:
                    pass
        print(f"[upload] {label} — timed out after {timeout_s}s", file=sys.stderr, flush=True)
        return False

    def _inject_file_input_hook(self, page):
        """Patch HTMLInputElement click/showPicker so native file dialog never opens.

        When Gemini creates a file input and calls .click() or .showPicker() on
        it, the patch stores the element reference instead of opening the OS
        dialog.  We can then use Playwright's set_input_files() on the
        intercepted element.
        """
        page.evaluate("""
        () => {
            if (window.__gemini_hook_installed) return;
            window.__gemini_hook_installed = true;

            const origClick = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function() {
                if (this.type === 'file') {
                    window.__gemini_file_input = this;
                    window.__gemini_hook_fired = true;
                    this.dispatchEvent(new Event('__file_input_intercepted__'));
                    return;
                }
                return origClick.call(this);
            };

            // Also hook showPicker (newer API, bypasses click)
            if (HTMLInputElement.prototype.showPicker) {
                const origShowPicker = HTMLInputElement.prototype.showPicker;
                HTMLInputElement.prototype.showPicker = function() {
                    if (this.type === 'file') {
                        window.__gemini_file_input = this;
                        window.__gemini_hook_fired = true;
                        return Promise.resolve();
                    }
                    return origShowPicker.call(this);
                };
            }

            // MutationObserver as safety net
            const observer = new MutationObserver((mutations) => {
                for (const m of mutations) {
                    for (const node of m.addedNodes) {
                        if (node.nodeType !== 1) continue;
                        if (node.tagName === 'INPUT' && node.type === 'file') {
                            window.__gemini_file_input = window.__gemini_file_input || node;
                            window.__gemini_hook_fired = true;
                        }
                        if (node.querySelectorAll) {
                            const fi = node.querySelector('input[type="file"]');
                            if (fi) {
                                window.__gemini_file_input = window.__gemini_file_input || fi;
                                window.__gemini_hook_fired = true;
                            }
                        }
                    }
                }
            });
            observer.observe(document.body, {childList: true, subtree: true});
        }
        """)

    def _has_upload_preview(self, page) -> bool:
        """Check if an uploaded image preview is visible in Gemini's input area."""
        try:
            found = page.evaluate("""
            () => {
                // Check ALL images on the page for upload indicators.
                // Gemini places the preview in a button ABOVE the textbox,
                // not inside the textbox container.
                const imgs = document.querySelectorAll('img');
                for (const img of imgs) {
                    if (!img.src) continue;
                    // The uploaded preview is a blob URL
                    if (img.src.startsWith('blob:')) {
                        // Verify it's a real image (not an icon)
                        const w = img.naturalWidth || img.width || 0;
                        if (w > 100) return 'blob-img:' + w + 'px';
                    }
                    // Check aria labels (Chinese: 图片预览, English: Image preview)
                    const aria = img.getAttribute('aria-label') || '';
                    if (aria.includes('预览') || aria.includes('preview')) return 'aria:' + aria;
                    // Check if the image is inside a button (upload preview pattern)
                    if (img.parentElement?.tagName === 'BUTTON' && w > 100) return 'btn-img:' + w + 'px';
                }

                // Check for upload preview buttons with images
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const aria = btn.getAttribute('aria-label') || '';
                    if (aria.includes('图片预览') || aria.includes('Image preview')) return 'btn-aria:' + aria;
                    if (aria.includes('移除') || aria.includes('Remove')) return 'btn-remove';
                    // Button contains an image with blob src
                    const btnImgs = btn.querySelectorAll('img');
                    for (const img of btnImgs) {
                        if (img.src && img.src.startsWith('blob:')) return 'btn-blob-img';
                    }
                }

                // Check for image-button class
                if (document.querySelector('button.image-button')) return 'image-button-class';
                if (document.querySelector('[data-upload-preview]')) return 'upload-preview-attr';

                // Check text content near the input
                const rt = document.querySelector('rich-textarea') ||
                          document.querySelector('[role="textbox"]');
                if (rt) {
                    const parent = rt.closest('form') || rt.parentElement;
                    if (parent) {
                        const text = parent.textContent || '';
                        if (text.includes('已上传') || text.includes('uploaded')) return 'text:uploaded';
                    }
                }

                return false;
            }
            """)
            if found:
                import sys
                print(f"[upload] preview detected: {found}", file=sys.stderr, flush=True)
                return True
        except Exception:
            pass
        return False

    def _count_generated_images(self, page) -> int:
        """Count how many AI-generated images are currently in the page."""
        try:
            return page.locator(GEMINI_SELECTORS["image_result"]).count()
        except Exception:
            return 0

    def _wait_for_image(self, page, poll_interval: float = 1.0) -> Optional[bytes]:
        """Poll until a new generated image appears, then download it."""
        deadline = time.time() + self.timeout
        seen_count = self._image_count_before

        while time.time() < deadline:
            # Check if generation is still in progress
            try:
                current_count = page.locator(GEMINI_SELECTORS["image_result"]).count()
                if current_count > seen_count:
                    # New image appeared — get the latest one
                    img = page.locator(GEMINI_SELECTORS["image_result"]).last
                    return self._download_image_element(img)
            except Exception:
                pass

            # Also check for any new img in the last message-content
            try:
                msg_contents = page.locator(GEMINI_SELECTORS["conversation"])
                if msg_contents.count() > 0:
                    last_msg = msg_contents.last
                    imgs_in_msg = last_msg.locator("img")
                    if imgs_in_msg.count() > 0:
                        last_img = imgs_in_msg.last
                        src = last_img.get_attribute("src") or ""
                        if src and src.startswith("blob:"):
                            result = self._download_image_element(last_img)
                            if result:
                                return result
            except Exception:
                pass

            # Check for error messages
            try:
                error_indicators = page.locator('text="出了点问题"')
                if error_indicators.count() > 0:
                    raise GeminiCDPError("Gemini 返回了错误")
            except GeminiCDPError:
                raise
            except Exception:
                pass

            time.sleep(poll_interval)

        return None

    def _download_image_element(self, img_locator) -> Optional[bytes]:
        """Download an image from a Playwright locator element."""
        try:
            src = img_locator.get_attribute("src") or ""
            if src.startswith("blob:"):
                # Try canvas conversion first (full original resolution)
                result = self._download_blob(img_locator)
                if result:
                    return result
                # Fallback: element screenshot
                try:
                    return img_locator.screenshot()
                except Exception:
                    pass
            elif src.startswith("http"):
                import requests
                resp = requests.get(src, timeout=60)
                resp.raise_for_status()
                return resp.content
            elif src.startswith("data:"):
                _, encoded = src.split(",", 1)
                return base64.b64decode(encoded)
        except Exception:
            pass
        # Last resort: screenshot the element
        try:
            return img_locator.screenshot()
        except Exception:
            pass
        return None

    def _download_blob(self, img_locator) -> Optional[bytes]:
        """Download a blob image by reading it via canvas conversion."""
        page = img_locator.page
        try:
            b64_data = page.evaluate(
                """(img) => {
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    return canvas.toDataURL('image/png').split(',')[1];
                }""",
                img_locator.element_handle(),
            )
            if b64_data:
                return base64.b64decode(b64_data)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Full-resolution download via keyboard navigation
    # ------------------------------------------------------------------

    def _download_full_res(self, page, timeout_s: float = 15.0) -> Optional[bytes]:
        """Download full-resolution image via CDP mouse events.

        Gemini's "下载完整尺寸的图片" button only responds to trusted
        (isTrusted) events.  CDP Input.dispatchMouseEvent produces trusted
        events.  We locate the download button via JS and click it with CDP.
        """
        import sys, tempfile, os
        import time as _time

        try:
            page.bring_to_front()
            page.wait_for_timeout(300)
        except Exception:
            pass

        # Dismiss any open overlays
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass

        cdp = page.context.new_cdp_session(page)
        try:
            cdp.send("Page.enable")
        except Exception:
            pass

        # Set download path to a temp directory
        dl_dir = tempfile.mkdtemp(prefix="gemini_hd_")
        try:
            cdp.send("Browser.setDownloadBehavior", {
                "behavior": "allowAndName",
                "downloadPath": dl_dir.replace("\\", "/"),
                "eventsEnabled": True,
            })
        except Exception:
            pass

        # Hover the last generated image to reveal action buttons, then
        # locate the "下载完整尺寸的图片" button and click it via CDP mouse.
        found = False
        try:
            # Scroll the last image into view and hover to reveal buttons
            img_el = page.locator("img.image.animate.loaded").last
            if img_el.count() > 0:
                img_el.scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                img_el.hover()
                page.wait_for_timeout(800)
        except Exception:
            pass

        # Try CDP mouse click — find button center via JS, then dispatch
        for _ in range(3):
            try:
                rect = page.evaluate("""() => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        const label = b.getAttribute('aria-label') || '';
                        if (label.includes('下载完整尺寸') || label.includes('download full')) {
                            const r = b.getBoundingClientRect();
                            return {x: r.left + r.width/2, y: r.top + r.height/2, label: label};
                        }
                    }
                    // Also try text content match
                    for (const b of btns) {
                        if (b.textContent.includes('下载完整尺寸') || b.textContent.includes('download full')) {
                            const r = b.getBoundingClientRect();
                            return {x: r.left + r.width/2, y: r.top + r.height/2, label: b.textContent.trim()};
                        }
                    }
                    return null;
                }""")
                if rect and rect.get("x", 0) > 0:
                    cdp.send("Input.dispatchMouseEvent", {
                        "type": "mouseMoved",
                        "x": rect["x"], "y": rect["y"],
                    })
                    cdp.send("Input.dispatchMouseEvent", {
                        "type": "mousePressed",
                        "x": rect["x"], "y": rect["y"],
                        "button": "left", "clickCount": 1,
                    })
                    cdp.send("Input.dispatchMouseEvent", {
                        "type": "mouseReleased",
                        "x": rect["x"], "y": rect["y"],
                        "button": "left", "clickCount": 1,
                    })
                    found = True
                    print(f"[hd] CDP mouse click on: {rect['label']}", file=sys.stderr, flush=True)
                    break
                else:
                    # Button not visible yet — try hovering image again
                    page.wait_for_timeout(500)
                    try:
                        img_el = page.locator("img.image.animate.loaded").last
                        if img_el.count() > 0:
                            img_el.hover()
                    except Exception:
                        pass
                    page.wait_for_timeout(500)
            except Exception as e:
                print(f"[hd] mouse click attempt: {e}", file=sys.stderr, flush=True)
                page.wait_for_timeout(500)

        if not found:
            # Fallback: Tab navigation as last resort
            print("[hd] mouse click failed, trying Tab navigation", file=sys.stderr, flush=True)
            for _ in range(10):
                cdp.send("Input.dispatchKeyEvent", {
                    "type": "rawKeyDown", "key": "Tab", "code": "Tab",
                    "windowsVirtualKeyCode": 9, "nativeVirtualKeyCode": 9,
                })
                cdp.send("Input.dispatchKeyEvent", {
                    "type": "keyUp", "key": "Tab", "code": "Tab",
                    "windowsVirtualKeyCode": 9, "nativeVirtualKeyCode": 9,
                })
                page.wait_for_timeout(200)
                try:
                    aria = page.evaluate(
                        "() => document.activeElement?.getAttribute('aria-label') || ''"
                    )
                except Exception:
                    aria = ""
                if "下载完整" in aria or "download full" in aria.lower():
                    cdp.send("Input.dispatchKeyEvent", {
                        "type": "rawKeyDown", "key": "Enter", "code": "Enter",
                        "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
                    })
                    cdp.send("Input.dispatchKeyEvent", {
                        "type": "char", "text": "\r",
                        "windowsVirtualKeyCode": 13,
                    })
                    cdp.send("Input.dispatchKeyEvent", {
                        "type": "keyUp", "key": "Enter", "code": "Enter",
                        "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
                    })
                    found = True
                    print("[hd] download triggered via Tab+Enter", file=sys.stderr, flush=True)
                    break

        if not found:
            print("[hd] download button not found", file=sys.stderr, flush=True)
            return None

        # Wait for the file to appear
        deadline = _time.time() + timeout_s
        while _time.time() < deadline:
            page.wait_for_timeout(500)
            try:
                files = [f for f in os.listdir(dl_dir)
                         if os.path.isfile(os.path.join(dl_dir, f))
                         and not f.endswith(".crdownload")]
                if files:
                    newest = max(files, key=lambda f: os.path.getmtime(
                        os.path.join(dl_dir, f)))
                    fpath = os.path.join(dl_dir, newest)
                    _time.sleep(0.5)
                    data = Path(fpath).read_bytes()
                    if len(data) > 50000:
                        print(f"[hd] downloaded {len(data)} bytes from {newest}",
                              file=sys.stderr, flush=True)
                        return data
            except Exception:
                continue

        print("[hd] timed out waiting for download", file=sys.stderr, flush=True)
        return None
